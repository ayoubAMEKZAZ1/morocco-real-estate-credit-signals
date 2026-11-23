"""End-to-end test with no external network: simulated BAM page -> download -> extraction ->
products -> simulated release API. Simulated date: 2017-05-20 (Q1-2017 is the latest completed quarter).

Run with pytest, or directly: python tests/test_pipeline_end_to_end.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools.mock_server import make_server  # noqa: E402

SAMPLES = os.environ.get("IPAI_SAMPLES", os.path.join(ROOT, "tests", "samples"))


def run(cfg_path, *extra, env=None):
    e = dict(os.environ, **(env or {}))
    p = subprocess.run([sys.executable, os.path.join(ROOT, "run_pipeline.py"), "run",
                        "--config", cfg_path, "--workers", "2", *extra],
                       capture_output=True, text=True, env=e)
    return p.returncode, p.stdout + p.stderr


def make_cfg(tmp, port):
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml"), encoding="utf-8"))
    cfg["sources"][0]["url"] = f"http://127.0.0.1:{port}/page"
    cfg["http"]["min_delay_seconds"] = 0
    cfg["http"]["backoff_seconds"] = 0
    cfg["publish"]["enabled"] = True
    cfg["publish"]["allow_insecure_http"] = True
    cfg["publish"]["block_on_errors"] = False
    cfg["viz"]["enabled"] = False
    for k in ("pdf_dir", "cache_dir", "output_dir"):
        cfg["paths"][k] = os.path.join(tmp, k)
    cfg["paths"]["state_file"] = os.path.join(tmp, "state.json")
    p = os.path.join(tmp, "config.yaml")
    yaml.safe_dump(cfg, open(p, "w", encoding="utf-8"), allow_unicode=True)
    return p


def run_scenarios():
    pdf = open(os.path.join(SAMPLES, "sample_Q1_2017.pdf"), "rb").read()
    old = open(os.path.join(SAMPLES, "sample_Q4_2016.pdf"), "rb").read()
    srv, got = make_server({"ipai-t1-2017-fr.pdf": pdf, "ipai-t4-2016-fr.pdf": old})
    port = srv.server_address[1]
    tmp = tempfile.mkdtemp()
    cfg = make_cfg(tmp, port)
    env = {"IPAI_API_URL": f"http://127.0.0.1:{port}/api", "IPAI_API_KEY": "test-key", "IPAI_AUDIENCE": "analytics"}
    results = {}

    # 1) outside the window (2017-04-10 = 10 days after quarter end): no network access
    rc, out = run(cfg, "--today", "2017-04-10", env=env)
    results["outside_window_skip"] = ("outside the window" in out
                                      and not os.path.exists(os.path.join(tmp, "pdf_dir", "ipai-t1-2017-fr.pdf")))

    # 2) inside the window: download, extraction, release
    rc, out = run(cfg, "--today", "2017-05-20", env=env)
    od = os.path.join(tmp, "output_dir")
    xlsx = os.path.join(od, "IPAI_quarterly_series.xlsx")
    results["pdf_downloaded"] = os.path.exists(os.path.join(tmp, "pdf_dir", "ipai-t1-2017-fr.pdf"))
    results["workbook_written"] = os.path.exists(xlsx)
    results["diagnostics_written"] = os.path.exists(os.path.join(od, "pipeline_diagnostics.xlsx"))
    results["released_once"] = len(got) == 1 and got[0]["has_audience"]
    from openpyxl import load_workbook
    wb = load_workbook(xlsx)
    results["20_sheets_plus_diagnostics"] = len(wb.sheetnames) == 21
    results["english_sheet_names"] = wb.sheetnames[0] == "01_Price_Global" and "04_Cat_Residential" in wb.sheetnames

    # 3) immediate rerun: nothing new, no second release
    rc, out = run(cfg, "--today", "2017-05-21", env=env)
    results["rerun_idempotent"] = len(got) == 1 and "already archived" in out

    # 4) invalid API key: failure reported (exit code 2), no crash
    rc, out = run(cfg, "--rebuild", "--force-publish", "--today", "2017-05-22",
                  env=dict(env, IPAI_API_KEY="wrong"))
    results["bad_key_reported"] = rc == 2 and "publish_failed" in open(
        os.path.join(od, "diagnostics_anomalies.csv"), encoding="utf-8").read()
    srv.shutdown()

    # 5) site answers 403: clean stop, WARN anomaly, no circumvention
    srv2, _ = make_server({"x.pdf": b"x"}, bam_403=True)
    tmp2 = tempfile.mkdtemp()
    cfg2 = make_cfg(tmp2, srv2.server_address[1])
    rc, out = run(cfg2, "--today", "2017-05-20", env=env)
    results["http_403_handled"] = "HTTP 403" in out and rc in (0, 2)
    srv2.shutdown()

    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(tmp2, ignore_errors=True)
    return results


def test_pipeline_end_to_end():
    results = run_scenarios()
    failed = [k for k, v in results.items() if not v]
    assert not failed, f"failed scenarios: {failed}"


if __name__ == "__main__":
    res = run_scenarios()
    for k, v in res.items():
        print(("OK    " if v else "FAILED"), k)
    sys.exit(0 if all(res.values()) else 1)
