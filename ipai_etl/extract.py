"""STAGE 2 - PDF processing and extraction (incremental).

Each PDF is processed once and its raw result is cached (key = file SHA-256 + engine version).
The series are re-assembled on every run from all cached results, including filling gaps from the
chart windows of later bulletins. This is fast.
"""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

EXT_DIR = os.path.join(os.path.dirname(__file__), "extractor")
sys.path.insert(0, EXT_DIR)
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

ENGINE_VERSION = "2.2"   # bump to invalidate the cache when extraction output changes


def _intkeys(o):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            try:
                k2 = int(k) if isinstance(k, str) and k.lstrip("-").isdigit() else k
            except ValueError:
                k2 = k
            out[k2] = _intkeys(v)
        return out
    if isinstance(o, list):
        return [_intkeys(x) for x in o]
    return o


def _process(path):
    from bulletin import process_bulletin
    try:
        return process_bulletin(path)
    except Exception as e:  # one failing PDF does not stop the batch
        import traceback
        fn = os.path.basename(path)
        return {"file": fn, "quarter": None, "diags": [
            {"file": fn, "quarter": None, "field": "general",
             "message": f"{e}\n{traceback.format_exc()}"}]}


def run_extract(cfg, state, rl, workers=3):
    from assemble import pick_primary, build_series, quarters_range
    cache_dir = cfg["paths"]["cache_dir"]
    pdf_dir = cfg["paths"]["pdf_dir"]
    todo, results = [], []
    for label, info in sorted(state["quarters"].items()):
        p = os.path.join(pdf_dir, info["file"])
        if not os.path.exists(p):
            rl.anomaly("ERROR", "pdf_missing", info["file"], f"{label}: archived file not found")
            continue
        cp = os.path.join(cache_dir, f"{info['sha256']}_{ENGINE_VERSION}.json")
        if os.path.exists(cp):
            with open(cp, encoding="utf-8") as f:
                results.append(_intkeys(json.load(f)))
        else:
            todo.append((p, cp))
    rl.step("2-extraction", "PDFs cached / to process", "OK", f"{len(results)} / {len(todo)}")
    if todo:
        if workers > 1 and len(todo) > 1:
            with ProcessPoolExecutor(max_workers=workers) as ex:
                outs = list(ex.map(_process, [p for p, _ in todo]))
        else:
            outs = [_process(p) for p, _ in todo]
        for (p, cp), r in zip(todo, outs):
            with open(cp, "w", encoding="utf-8") as f:
                json.dump(r, f, ensure_ascii=False)
            results.append(r)
            rl.step("2-extraction", f"{os.path.basename(p)}", "OK" if r.get("quarter") else "WARN",
                    r.get("quarter") or "quarter not detected")
    diagnostics = [d for r in results for d in r["diags"]]
    primary = pick_primary(results, diagnostics)
    S = build_series(primary)
    S["primary"] = primary
    return S, diagnostics
