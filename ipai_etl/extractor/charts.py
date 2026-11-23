"""Geometric reading of the IPAI bar charts (transaction counts exist only as chart bars).

Compared with vector_charts.py (v1):
- Read EVERY bar in the window shown by the bulletin (about 24 quarters), not only the last one.
  This fills quarters whose own bulletin is missing, unreadable or has no chart for that city;
  those values are labelled "revised" because they come from a later bulletin.
- Calibration: the y axis starts at ZERO (the bars' baseline), so
  value = k x (baseline - bar_top). One readable tick label is enough to fix k; with several,
  keep the k supported by the most ticks (rejects OCR errors).
- Tick labels: the PDF TEXT first (exact), otherwise OCR on a pdfplumber rendering (no poppler).
- If the national chart's title cannot be found, locate it by structure (3 bars per quarter).

The bulletins are in French; title patterns below match French text after accent stripping
(e.g. "evolution du nombre de transactions" = change in the number of transactions).
"""
import re
import unicodedata
from collections import defaultdict, Counter

import numpy as np

from vector_charts import get_bar_groups, get_horizontal_gridlines

OCR_DPI = 450


def norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


# ----------------------------------------------------------------------
# Page cache: words, lines and rendering, computed once
# ----------------------------------------------------------------------
class PageCache:
    def __init__(self, page):
        self.page = page
        self._words = None
        self._img = None

    @property
    def words(self):
        if self._words is None:
            self._words = self.page.extract_words()
        return self._words

    def lines(self, x_min=None):
        ws = self.words
        if x_min is not None:
            ws = [w for w in ws if w["x0"] >= x_min]
        buckets = defaultdict(list)
        for w in ws:
            buckets[round(w["top"])].append(w)
        out = []
        for top, items in buckets.items():
            items.sort(key=lambda w: w["x0"])
            out.append({"top": top, "x0": items[0]["x0"], "x1": items[-1]["x1"],
                        "text": " ".join(w["text"] for w in items)})
        out.sort(key=lambda l: l["top"])
        return out

    @property
    def image(self):
        if self._img is None:
            self._img = self.page.to_image(resolution=OCR_DPI).original.convert("L")
        return self._img


# ----------------------------------------------------------------------
# Tick labels: PDF text, otherwise OCR
# ----------------------------------------------------------------------
def text_ticks(pc, axis_x, region):
    """Numeric y-axis labels present as TEXT in the PDF. Returns [(y_centre, value)]."""
    _, top0, _, top1 = region
    cand = [w for w in pc.words
            if axis_x - 80 <= w["x0"] and w["x1"] <= axis_x + 3
            and top0 - 8 <= (w["top"] + w["bottom"]) / 2 <= top1 + 8]
    if not cand:
        return []
    cand.sort(key=lambda w: (w["top"] + w["bottom"]) / 2)
    rows, cur = [], [cand[0]]
    for w in cand[1:]:
        if abs((w["top"] + w["bottom"]) / 2 - (cur[-1]["top"] + cur[-1]["bottom"]) / 2) <= 2.5:
            cur.append(w)
        else:
            rows.append(cur)
            cur = [w]
    rows.append(cur)
    ticks = []
    for r in rows:
        r.sort(key=lambda w: w["x0"])
        s = re.sub(r"[\s  ]", "", "".join(w["text"] for w in r))
        if re.fullmatch(r"\d+", s):
            ticks.append((float(np.mean([(w["top"] + w["bottom"]) / 2 for w in r])), float(s)))
    return ticks


def ocr_ticks(pc, axis_x, gridline_tops):
    """OCR each tick label (fallback when the axis labels are drawn as vector outlines with no
    text). Returns {top: value|None}."""
    import pytesseract
    img = pc.image
    sc = OCR_DPI / 72.0
    out = {}
    for top in gridline_tops:
        x0, x1 = axis_x - 55, axis_x - 2
        box = (int(max(x0, 0) * sc), int((top - 6) * sc), int(x1 * sc), int((top + 6) * sc))
        if box[2] <= box[0] or box[3] <= box[1]:
            out[top] = None
            continue
        crop = img.crop(box)
        crop = crop.resize((crop.width * 2, crop.height * 2))
        txt = pytesseract.image_to_string(
            crop, config="--psm 7 -c tessedit_char_whitelist=0123456789").strip()
        txt = re.sub(r"[^\d]", "", txt)
        out[top] = int(txt) if txt else None
    return out


def fit_scale(labelled, baseline, tol=0.03):
    """labelled = [(top, value)]. Returns (k, n_inliers, n_labels), with
    value = k x (baseline - top). k is the scale supported by the most ticks (tolerance tol)."""
    pts = [(baseline - t, v) for t, v in labelled if baseline - t > 2 and v > 0]
    if not pts:
        return None, 0, 0
    best = None
    for d0, v0 in pts:
        k = v0 / d0
        inl = [(d, v) for d, v in pts if abs(v - k * d) <= tol * max(k * d, 1)]
        score = (len(inl), -sum(abs(v - k * d) / max(v, 1) for d, v in inl))
        if best is None or score > best[0]:
            best = (score, inl)
    inl = best[1]
    k = sum(d * v for d, v in inl) / sum(d * d for d, v in inl)
    return k, len(inl), len(pts)


def calibrate(pc, region, baseline, bars_x0):
    """Return (k, zero_top, info:str, warning|None)."""
    page = pc.page
    tops, axis_x = get_horizontal_gridlines(page, region, bars_x0=bars_x0)
    labelled, source = [], None
    # Axis zero = bottom of the bar rectangles. The "0" gridline is a thicker axis line offset by
    # about 0.2 pt; using it would bias short bars by about 1% (checked on Q4-2016).
    zero = baseline
    if axis_x is not None:
        ticks = text_ticks(pc, axis_x, region)
        if ticks and tops:
            for t in tops:
                near = min(ticks, key=lambda tk: abs(tk[0] - t))
                if abs(near[0] - t) <= 4.5:
                    labelled.append((t, near[1]))
        elif ticks and not tops:
            labelled = [(y, v) for y, v in ticks]
        if len(labelled) >= 2:
            source = "text"
    if len(labelled) < 2 and tops and axis_x is not None:
        ocr = ocr_ticks(pc, axis_x, tops)
        labelled = [(t, v) for t, v in ocr.items() if v is not None]
        source = "OCR"
    if not labelled:
        return None, zero, "", "no readable y-axis tick"
    k, n_in, n_lab = fit_scale(labelled, zero)
    if k is None:
        return None, zero, "", "calibration failed"
    warn = None
    if n_in < 3:
        warn = (f"calibration based on {n_in} tick(s) read by {source} "
                f"({n_lab} read); check manually")
    return k, zero, f"{source}:{n_in}/{n_lab}", warn


# ----------------------------------------------------------------------
# Full window of a bar chart
# ----------------------------------------------------------------------
def read_window(pc, region, expected_series):
    """Return {'window': {offset: [values]}, 'warning': str|None, 'info': str}.
    Offset 0 = last group (the bulletin's quarter), -1 = previous quarter, and so on. Missing groups
    (detected from the regular x spacing) are left out."""
    res = {"window": {}, "warning": None, "info": ""}
    groups, baseline = get_bar_groups(pc.page, region)
    if not groups:
        res["warning"] = "no bars detected in the region"
        return res
    bars_x0 = min(r["x0"] for g in groups for r in g)
    k, zero, info, warn = calibrate(pc, region, baseline, bars_x0)
    res["info"] = info
    res["k"] = k
    if k is None:
        res["warning"] = warn
        return res
    centers = [np.mean([(r["x0"] + r["x1"]) / 2 for r in g]) for g in groups]
    pitch = float(np.median(np.diff(centers))) if len(centers) > 1 else None
    msgs = [warn] if warn else []
    for g, c in zip(groups, centers):
        off = -int(round((centers[-1] - c) / pitch)) if pitch else 0
        g = sorted(g, key=lambda r: r["x0"])
        if len(g) != expected_series:
            if off == 0:
                msgs.append(f"last group: {len(g)} bars instead of {expected_series}")
            continue
        res["window"][off] = [round(k * (zero - r["top"])) for r in g]
    if 0 not in res["window"]:
        res["warning"] = "; ".join(msgs) or "last group unreadable"
        return res
    res["warning"] = "; ".join(msgs) or None
    return res


# ----------------------------------------------------------------------
# National chart (3 series): by title, otherwise by structure
# ----------------------------------------------------------------------
NATIONAL_TITLE_RE = re.compile(r"(evolution|variation) du nombre de transactions")
NEXT_TITLE_RE = re.compile(r"evolution|variation|indice")


def structural_charts(page, min_bars=10):
    """Find the bar charts on a page without using titles, by grouping rectangles on a shared
    baseline."""
    cl = defaultdict(list)
    for r in page.rects:
        if r["height"] > 1 and r["width"] < 14:
            cl[round(r["bottom"] * 2) / 2].append(r)
    charts = []
    for b, rs in cl.items():
        if len(rs) < min_bars:
            continue
        rs.sort(key=lambda r: r["x0"])
        seg = [rs[0]]
        segs = []
        for r in rs[1:]:
            if r["x0"] - seg[-1]["x1"] > 40:
                segs.append(seg)
                seg = [r]
            else:
                seg.append(r)
        segs.append(seg)
        for s in segs:
            if len(s) >= min_bars:
                charts.append({"baseline": b, "x0": s[0]["x0"], "x1": s[-1]["x1"],
                               "top": min(r["top"] for r in s)})
    return charts


def national_window(pdf, caches):
    """Return (window{offset: [residential, land, commercial]}, warning, info)."""
    warnings = []
    # 1) by title
    for pi, pc in enumerate(caches):
        page = pc.page
        lines = pc.lines(x_min=page.width * 0.3)
        title = next((l for l in lines if NATIONAL_TITLE_RE.search(norm(l["text"]))), None)
        if not title:
            continue
        below = [l for l in lines if l["top"] > title["top"] + 10]
        nxt = next((l for l in below if NEXT_TITLE_RE.search(norm(l["text"]))), None)
        top1 = nxt["top"] - 5 if nxt else page.height - 60
        region = (page.width * 0.3, title["top"] + 10, page.width * 0.99, top1)
        r = read_window(pc, region, 3)
        if r["window"]:
            return r["window"], r["warning"], r["info"]
        warnings.append(f"p.{pi + 1} (title): {r['warning']}")
    # 2) by structure: a chart whose last group has 3 bars
    for pi, pc in enumerate(caches):
        for ch in structural_charts(pc.page):
            region = (ch["x0"] - 90, ch["baseline"] - 240, ch["x1"] + 5, ch["baseline"] + 3)
            r = read_window(pc, region, 3)
            if r["window"] and len(r["window"]) >= 8:
                return r["window"], "chart located by its structure (title not found)", r["info"]
    return {}, "; ".join(warnings) or "national chart not found", ""


# ----------------------------------------------------------------------
# City charts
# ----------------------------------------------------------------------
from names import CITY_FR_TO_EN  # noqa: E402

ALL_CITIES = list(CITY_FR_TO_EN.values())          # English display names
DOMINANT = ["Rabat", "Casablanca", "Marrakech", "Tangier"]
_NORM2CITY = {norm(fr): en for fr, en in CITY_FR_TO_EN.items()}   # matched on the French spelling
_ALT = "|".join(re.escape(k) for k in _NORM2CITY)
EMBEDDED = re.compile(rf"transactions? a ({_ALT})\b")
STANDALONE = re.compile(rf"\b({_ALT})\b")


def city_windows(pdf, caches):
    """Return {city: {'window': {offset: [v]}, 'warning', 'info'}} for the four dominant cities
    that have a chart in the bulletin ('quelques grandes villes' marks the ten-city table page)."""
    anchors = {}
    for pi, pc in enumerate(caches):
        txt = norm(pc.page.extract_text() or "")
        if "quelques grandes villes" in txt:
            continue
        for l in pc.lines(x_min=pc.page.width * 0.45):
            t = norm(l["text"].strip())
            m = EMBEDDED.search(t)
            if m and _NORM2CITY[m.group(1)] not in anchors:
                anchors[_NORM2CITY[m.group(1)]] = (pi, l["top"])
                continue
            m2 = STANDALONE.search(t)
            if m2 and len(t) < 40 and _NORM2CITY[m2.group(1)] not in anchors:
                anchors[_NORM2CITY[m2.group(1)]] = (pi, l["top"])
    by_page = defaultdict(list)
    for c, (pi, top) in anchors.items():
        by_page[pi].append((top, c))
    out = {}
    for pi, items in by_page.items():
        items.sort()
        page = caches[pi].page
        for i, (top, c) in enumerate(items):
            top1 = items[i + 1][0] - 5 if i + 1 < len(items) else page.height - 40
            region = (page.width * 0.45, top + 12, page.width * 0.98, top1)
            if c in DOMINANT:
                out[c] = read_window(caches[pi], region, 1)
    return out
