"""STAGE 3 - Output products: the .xlsx workbook (20 sheets), a long pandas table (CSV, the
format loaded into a data mart) and the diagnostics file."""
import contextlib
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "extractor"))
from assemble import CATS  # noqa: E402
from charts import ALL_CITIES, DOMINANT  # noqa: E402
from excel_out import write_workbook  # noqa: E402

WORKBOOK_NAME = "IPAI_quarterly_series.xlsx"


def _qsort(x):
    """Sort key for 'Q4-2016' style labels; other values sort as themselves."""
    if isinstance(x, str) and x.startswith("Q") and "-" in x:
        return int(x[3:]) * 4 + int(x[1])
    return x


def build_long(S, run_id, extracted_at):
    """Long table (one row per value): the data-mart loading format."""
    rows = []

    def add(series, subseries, t, indicator, val, src, unit):
        if val is None:
            return
        rows.append({"series": series, "subseries": subseries, "quarter": t, "indicator": indicator,
                     "value": val, "unit": unit, "value_source": src,
                     "run_id": run_id, "extracted_at": extracted_at})

    for t in S["quarters"]:
        b = S["tables"].get(t)
        if b:
            for cat in CATS:
                add("category", cat, t, "price_change_qoq_pct", b.get("price_qoq", {}).get(cat), "published", "%")
                add("category", cat, t, "price_change_yoy_pct", b.get("price_yoy", {}).get(cat), "published", "%")
                add("category", cat, t, "transactions_change_qoq_pct", b.get("trans_pct_qoq", {}).get(cat), "published", "%")
                add("category", cat, t, "transactions_change_yoy_pct", b.get("trans_pct_yoy", {}).get(cat), "published", "%")
            for city in ALL_CITIES:
                v = b.get("cities10", {}).get(city, {})
                add("city10", city, t, "price_change_qoq_pct", v.get("price_qoq"), "published", "%")
                add("city10", city, t, "transactions_change_qoq_pct", v.get("trans_qoq"), "published", "%")
        e = S["nat"].get(t)
        if e:
            for cat in CATS:
                add("category", cat, t, "transactions_count", e[0][cat], e[1], "count")
    for city in DOMINANT:
        for t, (v, src) in S["city"][city].items():
            add("dominant_city", city, t, "transactions_count", v, src, "count")
    df = pd.DataFrame(rows)
    return df.sort_values(["series", "subseries", "indicator", "quarter"],
                          key=lambda c: c.map(_qsort)).reset_index(drop=True)


def write_products(S, extraction_diags, cfg, run_id, extracted_at):
    out = cfg["paths"]["output_dir"]
    xlsx = os.path.join(out, WORKBOOK_NAME)
    write_workbook(S, extraction_diags, xlsx)
    long_df = build_long(S, run_id, extracted_at)
    csv_path = os.path.join(out, "ipai_long.csv")
    long_df.to_csv(csv_path, index=False, encoding="utf-8")
    return xlsx, csv_path, long_df


def write_diagnostic(rl, extraction_diags, completeness, cfg, run_id, xlsx=True):
    out = cfg["paths"]["output_dir"]
    path = os.path.join(out, "pipeline_diagnostics.xlsx")
    writer = pd.ExcelWriter(path, engine="openpyxl") if xlsx else contextlib.nullcontext()
    with writer as xw:
        if xlsx:
            pd.DataFrame(rl.steps).to_excel(xw, sheet_name="Processing_steps", index=False)
            pd.DataFrame(rl.anomalies or [{"severity": "-", "category": "-", "subject": "-",
                                           "message": "no anomaly"}]).to_excel(xw, sheet_name="Anomalies", index=False)
            pd.DataFrame(completeness).to_excel(xw, sheet_name="Series_completeness", index=False)
            pd.DataFrame(extraction_diags or [{"message": "-"}]).to_excel(xw, sheet_name="Extraction_messages", index=False)
            for ws in xw.book.worksheets:
                ws.freeze_panes = "A2"
                for col in ws.columns:
                    ws.column_dimensions[col[0].column_letter].width = min(
                        max(len(str(c.value or "")) for c in col[:60]) + 2, 90)
    pd.DataFrame(rl.steps).to_csv(os.path.join(out, "diagnostics_steps.csv"), index=False)
    pd.DataFrame(rl.anomalies).to_csv(os.path.join(out, "diagnostics_anomalies.csv"), index=False)
    return path
