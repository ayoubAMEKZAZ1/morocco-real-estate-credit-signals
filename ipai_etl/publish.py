"""STAGE 4 (optional, off by default) - Send the release to an HTTP API.

Expected server contract (adapt to your own endpoint):
  POST {IPAI_API_URL}   (multipart/form-data)
    headers: <key_header>: <API key>; Idempotency-Key: <SHA-256 of the manifest>
    fields : audience (optional label from IPAI_AUDIENCE), run_id, quarter, manifest (JSON)
    files  : one `files` field per product (xlsx, csv, diagnostics)
  Expected response: 200, 201 or 202.
Access control on the `audience` label must be enforced by the server; the client only
authenticates and labels the release.
The API key is read from the environment only and is never logged.
"""
import hashlib
import json
import os
import time

import requests

from .state import now_iso


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def build_manifest(files, run_id, quarter):
    return {"run_id": run_id, "quarter": quarter, "created_at": now_iso(), "schema": "ipai-release/1",
            "files": [{"name": os.path.basename(p), "sha256": sha256_file(p), "bytes": os.path.getsize(p)}
                      for p in files]}


def run_publish(cfg, state, rl, files, run_id, quarter, dry_run=False, force=False):
    pc = cfg["publish"]
    manifest = build_manifest(files, run_id, quarter)
    mpath = os.path.join(cfg["paths"]["output_dir"], "manifest.json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    if not pc.get("enabled", False):
        rl.step("4-publish", "publishing disabled (config)", "SKIP")
        return False
    if pc.get("block_on_errors", True) and rl.has_errors() and not force:
        rl.step("4-publish", "blocked by ERROR anomalies", "BLOCKED", "review, then rerun with --force-publish")
        return False
    idem = hashlib.sha256(json.dumps(manifest["files"], sort_keys=True).encode()).hexdigest()
    if state.get("last_publish") and state["last_publish"].get("idempotency") == idem and not force:
        rl.step("4-publish", "same product as the last release", "SKIP")
        return False
    url, key = os.environ.get(pc["url_env"]), os.environ.get(pc["key_env"])
    audience = os.environ.get(pc.get("audience_env", "IPAI_AUDIENCE"), "")
    if dry_run:
        rl.step("4-publish", "dry run", "SKIP", f"{len(files)} file(s), manifest {mpath}")
        return False
    if not (url and key):
        rl.step("4-publish", "missing environment variables", "ERROR", f"{pc['url_env']} and {pc['key_env']} required")
        rl.anomaly("ERROR", "publish_config", "-", "API URL or key not configured")
        return False
    if not url.lower().startswith("https://") and not pc.get("allow_insecure_http"):
        rl.step("4-publish", "non-HTTPS URL refused", "ERROR", "allow_insecure_http=false")
        rl.anomaly("ERROR", "publish_security", "-", "unencrypted transmission refused")
        return False
    last_err = None
    for attempt in range(1, pc["max_retries"] + 1):
        handles = [open(p, "rb") for p in files]
        try:
            r = requests.post(
                url,
                headers={pc["key_header"]: key, "Idempotency-Key": idem},
                data={"audience": audience, "run_id": run_id, "quarter": quarter, "manifest": json.dumps(manifest)},
                files=[("files", (os.path.basename(p), h)) for p, h in zip(files, handles)],
                timeout=pc["timeout_seconds"],
            )
        except requests.RequestException as e:
            last_err = str(e)
        else:
            if r.status_code in (200, 201, 202):
                state["last_publish"] = {"at": now_iso(), "run_id": run_id, "quarter": quarter,
                                         "idempotency": idem, "http": r.status_code}
                rl.step("4-publish", "release sent", "OK", f"HTTP {r.status_code}")
                return True
            last_err = f"HTTP {r.status_code}"
            if r.status_code in (400, 401, 403, 404, 409, 422):
                break  # retrying will not help
        finally:
            for h in handles:
                h.close()
        time.sleep(2 * attempt)
    rl.step("4-publish", "transmission failed", "ERROR", last_err or "")
    rl.anomaly("ERROR", "publish_failed", "-", last_err or "")
    return False
