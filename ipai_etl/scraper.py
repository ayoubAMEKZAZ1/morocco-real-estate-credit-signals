"""STAGE 1 - Detect and download new IPAI bulletins.

Principles:
- Query the network ONLY inside the expected publication window of the latest completed quarter,
  at most once every `check_every_days` days.
- Politeness: declared User-Agent, minimum delay between requests, a hard cap on requests per
  check, robots.txt respected, backoff on errors.
- No circumvention: if the site answers 403 or 429, stop and report it (no identity rotation,
  no retrying).
- A PDF is archived only after validation: %PDF header, minimum size, and the quarter read INSIDE
  the document must equal the expected quarter.
"""
import hashlib
import os
import re
import sys
import time
import urllib.robotparser
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from . import quarters as Q
from .state import now_iso

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "extractor"))
from quarter_detect import detect_quarter  # noqa: E402

QUARTER_IN_URL = re.compile(r"t([1-4])(?:[\s_\-]|%20)*(20\d{2})", re.I)


class Blocked(Exception):
    pass


class Http:
    def __init__(self, cfg, runlog):
        self.cfg, self.rl = cfg["http"], runlog
        self.s = requests.Session()
        self.s.headers["User-Agent"] = self.cfg["user_agent"]
        self.n = 0
        self._last = 0.0
        self._robots = {}

    def _allowed(self, url):
        if not self.cfg.get("respect_robots_txt", True):
            return True
        host = "{0.scheme}://{0.netloc}".format(urlparse(url))
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.s.get(host + "/robots.txt", timeout=self.cfg["timeout_seconds"])
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except requests.RequestException:
                rp.parse([])
            self._robots[host] = rp
        return self._robots[host].can_fetch(self.cfg["user_agent"], url)

    def get(self, url, stream=False):
        if self.n >= self.cfg["max_requests_per_check"]:
            raise Blocked("request cap per check reached")
        if not self._allowed(url):
            raise Blocked(f"robots.txt disallows {url}")
        last_exc = None
        for attempt in range(1, self.cfg["max_retries"] + 1):
            wait = self.cfg["min_delay_seconds"] - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            self.n += 1
            try:
                r = self.s.get(url, timeout=self.cfg["timeout_seconds"], stream=stream)
            except requests.RequestException as e:
                last_exc = e
                time.sleep(self.cfg["backoff_seconds"] * attempt)
                continue
            if r.status_code in (403, 429):
                raise Blocked(f"HTTP {r.status_code} on {url} (automated access refused)")
            if r.status_code >= 500:
                last_exc = RuntimeError(f"HTTP {r.status_code}")
                time.sleep(self.cfg["backoff_seconds"] * attempt)
                continue
            return r
        raise RuntimeError(f"network failure on {url}: {last_exc}")


def decide_check(cfg, state, today, force=False):
    """Return (check now?, target quarter, reason)."""
    target = Q.latest_completed_quarter(today)
    if target in state["quarters"]:
        return False, target, f"{target} already archived"
    if force:
        return True, target, "forced check"
    s = cfg["schedule"]
    w0, w1 = Q.window(target, s["window_start_day"], s["window_end_day"])
    if today < w0:
        return False, target, f"outside the window (opens on {w0.isoformat()})"
    last = state["last_check"].get(target)
    if last:
        d = datetime.strptime(last[:10], "%Y-%m-%d").date()
        if (today - d).days < s["check_every_days"]:
            return False, target, f"last check {(today - d).days} day(s) ago (< {s['check_every_days']})"
    if today > w1:
        return True, target, f"window closed ({w1.isoformat()}); weekly catch-up check" \
            if (not last or (today - datetime.strptime(last[:10], '%Y-%m-%d').date()).days >= 7) \
            else "window closed, waiting"
    return True, target, f"inside the window {w0.isoformat()} to {w1.isoformat()}"


def discover_urls(cfg, http, target, rl):
    """Return the ordered list of candidate (source, url) pairs for `target`."""
    q, y = Q.parse_label(target)
    found = []
    for src in cfg["sources"]:
        if not src.get("enabled"):
            continue
        try:
            if src["type"] == "page":
                r = http.get(src["url"])
                if r.status_code != 200:
                    rl.step("1-scraping", f"{src['name']}: page", "WARN", f"HTTP {r.status_code}")
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                n = 0
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if ".pdf" not in href.lower():
                        continue
                    full = urljoin(src["url"], href)
                    m = QUARTER_IN_URL.search(full) or QUARTER_IN_URL.search(a.get_text(" ", strip=True))
                    n += 1
                    if m and int(m.group(1)) == q and int(m.group(2)) == y:
                        found.append((src["name"], full))
                rl.step("1-scraping", f"{src['name']}: page parsed", "OK",
                        f"{n} PDF link(s), {sum(1 for s, _ in found if s == src['name'])} for {target}")
            elif src["type"] == "pattern":
                for tpl in src["url_templates"]:
                    found.append((src["name"], tpl.format(q=q, year=y)))
        except Blocked:
            raise
        except Exception as e:
            rl.step("1-scraping", f"{src['name']}", "WARN", str(e))
    return found


def _download(http, url, dest_tmp, min_size):
    r = http.get(url, stream=True)
    if r.status_code == 404:
        return None, "404"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    h = hashlib.sha256()
    size = 0
    with open(dest_tmp, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
            h.update(chunk)
            size += len(chunk)
    with open(dest_tmp, "rb") as f:
        head = f.read(5)
    if head != b"%PDF-":
        return None, "not a PDF"
    if size < min_size:
        return None, f"file too small ({size} bytes)"
    return {"sha256": h.hexdigest(), "size": size}, None


def sync_state_from_disk(cfg, state, rl):
    """Register PDFs already present in pdf_dir (first run)."""
    d = cfg["paths"]["pdf_dir"]
    known = {v["file"] for v in state["quarters"].values()}
    for fn in sorted(os.listdir(d)):
        if not fn.lower().endswith(".pdf") or fn in known:
            continue
        p = os.path.join(d, fn)
        try:
            qi = detect_quarter(p)
        except Exception as e:
            rl.anomaly("WARN", "pdf_unreadable", fn, str(e))
            continue
        if not qi:
            rl.anomaly("WARN", "quarter_not_detected", fn, "quarter not found in the PDF")
            continue
        label = qi[2]
        with open(p, "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()
        if label in state["quarters"]:
            rl.anomaly("INFO", "duplicate", fn, f"{label} already registered by {state['quarters'][label]['file']}")
            continue
        state["quarters"][label] = {"file": fn, "sha256": sha, "url": None,
                                    "source": "manual drop", "registered_at": now_iso()}
        rl.step("1-scraping", f"existing archive registered: {fn}", "OK", label)


def run_scrape(cfg, state, rl, today=None, force=False):
    """Return True if a NEW bulletin was archived."""
    today = today or date.today()
    sync_state_from_disk(cfg, state, rl)
    do, target, reason = decide_check(cfg, state, today, force)
    rl.step("1-scraping", f"check decision for {target}", "OK" if do else "SKIP", reason)
    if not do:
        w0, w1 = Q.window(target, cfg["schedule"]["window_start_day"], cfg["schedule"]["window_end_day"])
        if target not in state["quarters"] and today > w1:
            rl.anomaly("ERROR", "bulletin_missing", target,
                       f"no bulletin archived although the window closed on {w1.isoformat()}")
        return False
    state["last_check"][target] = now_iso()
    http = Http(cfg, rl)
    try:
        candidates = discover_urls(cfg, http, target, rl)
        if not candidates:
            rl.step("1-scraping", "no candidate URL", "SKIP",
                    f"bulletin {target} not published yet, or source disabled")
            return False
        for name, url in candidates:
            tmp = os.path.join(cfg["paths"]["pdf_dir"], f".dl_{target}.part")
            info, err = _download(http, url, tmp, cfg["pdf_validation"]["min_size_bytes"])
            if err:
                rl.step("1-scraping", f"{name}: {url}", "SKIP" if err == "404" else "WARN", err)
                if os.path.exists(tmp):
                    os.remove(tmp)
                continue
            qi = detect_quarter(tmp)
            if not qi or qi[2] != target:
                rl.anomaly("ERROR", "pdf_inconsistent", url,
                           f"content shows {qi[2] if qi else 'no quarter'}, expected {target}; rejected")
                os.remove(tmp)
                continue
            fn = f"ipai-t{qi[0]}-{qi[1]}-fr.pdf"   # same naming as the official files (French-language edition)
            os.replace(tmp, os.path.join(cfg["paths"]["pdf_dir"], fn))
            state["quarters"][target] = {"file": fn, "sha256": info["sha256"], "url": url,
                                         "source": name, "size": info["size"], "downloaded_at": now_iso()}
            rl.step("1-scraping", f"bulletin {target} downloaded", "OK", f"{fn} ({info['size']} bytes) from {name}")
            return True
    except Blocked as e:
        rl.anomaly("WARN", "access_blocked", target, str(e))
        rl.step("1-scraping", "check stopped", "WARN", str(e))
    except Exception as e:
        rl.anomaly("WARN", "scraping_error", target, str(e))
    return False
