#!/usr/bin/env python3
"""IPAI ETL pipeline orchestrator.

  python run_pipeline.py run                 # full cycle (cron-friendly: decides by itself whether to act)
  python run_pipeline.py run --force-check   # network check outside the window
  python run_pipeline.py run --rebuild       # rebuild the products even without a new bulletin
  python run_pipeline.py run --dry-run-publish
  python run_pipeline.py status
Exit codes: 0 OK or nothing to do; 1 runtime error; 2 ERROR anomalies (publishing blocked).
"""
import argparse
import logging
import os
import sys
import traceback
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ipai_etl.config import load_config  # noqa: E402
from ipai_etl.runlog import RunLog  # noqa: E402
from ipai_etl.state import load_state, save_state, now_iso  # noqa: E402
from ipai_etl import quarters as Q  # noqa: E402
from ipai_etl.scraper import run_scrape  # noqa: E402


def cmd_status(cfg):
    st = load_state(cfg["paths"]["state_file"])
    target = Q.latest_completed_quarter(date.today())
    print(f"Latest completed quarter: {target}")
    print(f"Archived bulletins: {len(st['quarters'])} ({', '.join(sorted(st['quarters'], key=Q.qidx))})")
    w = Q.window(target, cfg["schedule"]["window_start_day"], cfg["schedule"]["window_end_day"])
    print(f"Monitoring window for {target}: {w[0]} -> {w[1]}")
    print(f"Last check: {st['last_check'].get(target, 'never')}")
    print(f"Last release: {st['last_publish']}")
    return 0


def cmd_run(cfg, args):
    today = date.fromisoformat(args.today) if args.today else date.today()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rl = RunLog(run_id)
    state_path = cfg["paths"]["state_file"]
    state = load_state(state_path)
    code = 0
    try:
        # ---- Stage 1: detection and download
        new = run_scrape(cfg, state, rl, today=today, force=args.force_check)
        save_state(state_path, state)
        out_xlsx = os.path.join(cfg["paths"]["output_dir"], "IPAI_quarterly_series.xlsx")
        if not (new or args.rebuild or not os.path.exists(out_xlsx)):
            rl.step("0-orchestration", "nothing new: stages 2-4 not run", "SKIP")
        else:
            if not state["quarters"]:
                rl.anomaly("ERROR", "no_bulletin", "-", "no PDF in the archive")
            else:
                from ipai_etl.extract import run_extract
                from ipai_etl.outputs import write_products, write_diagnostic
                from ipai_etl.quality import completeness, run_checks
                from ipai_etl.publish import run_publish
                # ---- Stage 2: extraction
                S, ext_diags = run_extract(cfg, state, rl, workers=args.workers)
                # ---- Stage 3: output products, quality checks, diagnostics
                prev_long = os.path.join(cfg["paths"]["output_dir"], "ipai_long.csv")
                prev_copy = prev_long + ".prev"
                if os.path.exists(prev_long):
                    os.replace(prev_long, prev_copy)
                xlsx, csv_path, long_df = write_products(S, ext_diags, cfg, run_id, now_iso())
                rl.step("3-output", ".xlsx workbook and long pandas table written", "OK",
                        f"{os.path.basename(xlsx)}, {len(long_df)} rows")
                last = max(S["tables"], key=Q.qidx)
                run_checks(S, long_df, cfg, rl, state, prev_copy if os.path.exists(prev_copy) else None, today=today)
                comp = completeness(S, Q.latest_completed_quarter(today))
                diag = write_diagnostic(rl, ext_diags, comp, cfg, run_id)
                rl.step("3-output", "diagnostics file written", "OK", os.path.basename(diag))
                # ---- Stage 3b (optional): automatic dashboards (a failure is a warning, never blocking)
                viz_files = []
                vcfg = cfg.get("viz") or {}
                if vcfg.get("enabled", False):
                    try:
                        from ipai_viz.build import build as build_viz
                        vout = os.path.join(cfg["paths"]["output_dir"], "viz")
                        res = build_viz(xlsx, vout, vcfg.get("config"), vcfg.get("tableau_dir"))
                        rl.step("3b-viz", "dashboards generated", "OK", vout)
                        if vcfg.get("include_html_in_publish", False):
                            viz_files = [os.path.join(vout, "IPAI_dashboards.html")]
                    except Exception as e:
                        rl.anomaly("WARN", "viz", "-", f"dashboard generation failed: {e}")
                        rl.step("3b-viz", "dashboards", "WARN", str(e)[:200])
                # ---- Stage 4: publishing (optional)
                files = [xlsx, csv_path, diag] + viz_files
                run_publish(cfg, state, rl, files, run_id, last,
                            dry_run=args.dry_run_publish, force=args.force_publish)
                write_diagnostic(rl, ext_diags, comp, cfg, run_id, xlsx=False)  # CSV logs including stage 4
                if rl.has_errors():
                    code = 2
    except Exception as e:
        rl.step("0-orchestration", "exception", "ERROR", f"{e}\n{traceback.format_exc()}")
        code = 1
    state["runs"] = (state.get("runs", []) + [{"run_id": run_id, "at": now_iso(), "code": code}])[-50:]
    save_state(state_path, state)
    for s in rl.steps:
        print(f"{s['status']:8} {s['stage']:16} {s['action']} {s['detail'][:150]}")
    n_err = sum(a["severity"] == "ERROR" for a in rl.anomalies)
    n_w = sum(a["severity"] == "WARN" for a in rl.anomalies)
    print(f"\nrun {run_id}: code {code}, {n_err} error(s), {n_w} warning(s)")
    return code


def main():
    ap = argparse.ArgumentParser(description="IPAI ETL pipeline")
    ap.add_argument("command", choices=["run", "status"])
    ap.add_argument("--config", default=None)
    ap.add_argument("--force-check", action="store_true", help="network check even outside the window")
    ap.add_argument("--rebuild", action="store_true", help="rebuild the products without a new bulletin")
    ap.add_argument("--dry-run-publish", action="store_true")
    ap.add_argument("--force-publish", action="store_true", help="publish despite ERROR anomalies or an identical product")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--today", default=None, help="simulate today's date (YYYY-MM-DD), for tests")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    sys.exit(cmd_status(cfg) if args.command == "status" else cmd_run(cfg, args))


if __name__ == "__main__":
    main()
