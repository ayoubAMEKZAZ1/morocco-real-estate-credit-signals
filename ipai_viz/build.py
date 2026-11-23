#!/usr/bin/env python3
"""Generate the IPAI dashboards from the pipeline workbook.

    python -m ipai_viz.build --xlsx data/output/IPAI_quarterly_series.xlsx --out data/output/viz
    (--tableau-dir FOLDER also writes the 4 CSVs into the folder read by the Tableau workbook)
"""
import argparse
import os
import sys
from datetime import date

import matplotlib

matplotlib.use("Agg")
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from ipai_viz.load import HIST_COLS, load_workbook_series  # noqa: E402
from ipai_viz import transform as T  # noqa: E402
from ipai_viz.forecast_adapter import run_forecasts, validation_summary  # noqa: E402
from ipai_viz import render  # noqa: E402
from ipai_viz.report_html import build_html  # noqa: E402


def load_cfg(path=None):
    path = path or os.path.join(HERE, "viz_config.yaml")
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_dir"] = os.path.dirname(os.path.abspath(path))
    return cfg


def build(xlsx, out_dir, cfg_path=None, tableau_dir=None):
    cfg = load_cfg(cfg_path)
    notes = []
    os.makedirs(out_dir, exist_ok=True)
    hist, last, msgs = load_workbook_series(xlsx, cfg["window"]["first_quarter"])
    notes += msgs
    first = hist.Quarter.iloc[0]
    notes.append(f"{hist.Quarter.nunique()} quarters loaded: {first} to {last} "
                 f"({len(hist)} category x quarter rows).")
    if cfg["strict_twb_mode"]:
        notes.append("STRICT .twb MODE on: the 3 differences of the Tableau workbook are reproduced as they are.")
    else:
        notes.append("Build-guide method applied (Global combo = Global category; margin = simple spread; "
                     "seasonality = average). The current .twb differs on these 3 points; see viz_config.yaml.")

    fprev, fmsgs = run_forecasts(hist, last, cfg["window"]["forecast_horizon"])
    notes += fmsgs
    n_ok, n_tot, _ = validation_summary(hist)
    sg_path = cfg["signals_csv"] if os.path.isabs(cfg["signals_csv"]) else os.path.join(cfg["_dir"], cfg["signals_csv"])
    sg = pd.read_csv(sg_path, encoding="utf-8-sig")
    if last != cfg["signals_written_up_to"]:
        notes.append(f"Qualitative signals written for {cfg['signals_written_up_to']}; data run to {last}: "
                     f"review data/signals.csv, then update signals_written_up_to.")
    if n_tot < 8:
        notes.append(f"Validation summary computed on {n_tot}/8 series only (incomplete series).")
    notes.append("Winning model per series (WINNING_MODEL) kept as validated in September 2026; "
                 "it is not re-selected automatically (see ipai_viz/forecast/models.py).")

    D = {"hist": hist, "last": last, "first": first, "fprev": fprev, "signals": sg, "cfg": cfg,
         "signals_up_to": cfg["signals_written_up_to"], "validation": (n_ok, n_tot),
         "date": date.today().isoformat()}
    figs, variants = render.build_dashboards(D)
    annex = render.build_forecast_grid(D)
    so = cfg["outputs"]
    dash_dir = os.path.join(out_dir, "dashboards")
    os.makedirs(dash_dir, exist_ok=True)
    for name, fig in figs.items():
        if so.get("png"):
            fig.savefig(os.path.join(dash_dir, f"{name}.png"), dpi=200, facecolor="white")
        if so.get("svg"):
            fig.savefig(os.path.join(dash_dir, f"{name}.svg"), facecolor="white")
    if so.get("pdf"):
        from matplotlib.backends.backend_pdf import PdfPages
        with PdfPages(os.path.join(out_dir, "IPAI_dashboards.pdf")) as pdf:
            for fig in list(figs.values()) + [annex]:
                pdf.savefig(fig, facecolor="white")
    if so.get("html"):
        meta = f"Data {first} to {last} · source workbook: {os.path.basename(xlsx)} · generated {D['date']}"
        build_html(figs, variants, annex, notes, meta, os.path.join(out_dir, "IPAI_dashboards.html"))

    if so.get("tableau_csv"):
        cat_rank = {c: i for i, c in enumerate(T.CATS)}
        fh = hist.assign(_r=hist.Category.map(cat_rank)).sort_values(["Chrono_order", "_r"])[HIST_COLS]
        csv_files = {"fact_history.csv": fh, "dim_quarter.csv": T.dim_quarter(hist, fprev),
                     "fact_forecasts.csv": fprev, "dim_signals.csv": sg}
        for d in [os.path.join(out_dir, "tableau_csv")] + ([tableau_dir] if tableau_dir else []):
            os.makedirs(d, exist_ok=True)
            for fn, df in csv_files.items():
                df.to_csv(os.path.join(d, fn), index=False, encoding="utf-8-sig")
    pd.DataFrame({"note": notes}).to_csv(os.path.join(out_dir, "viz_diagnostics.csv"), index=False, encoding="utf-8-sig")
    import matplotlib.pyplot as plt
    plt.close("all")
    return {"out": out_dir, "last": last, "first": first, "notes": notes, "fprev_rows": len(fprev),
            "validation": (n_ok, n_tot)}


def main():
    ap = argparse.ArgumentParser(description="Generate the IPAI dashboards from the pipeline workbook")
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--out", default="viz")
    ap.add_argument("--config", default=None)
    ap.add_argument("--tableau-dir", default=None, help="folder read by the Tableau workbook (CSVs overwritten)")
    a = ap.parse_args()
    r = build(a.xlsx, a.out, a.config, a.tableau_dir)
    print(f"Dashboards generated in {r['out']} ({r['first']} to {r['last']}).")
    for n in r["notes"]:
        print(" -", n)


if __name__ == "__main__":
    main()
