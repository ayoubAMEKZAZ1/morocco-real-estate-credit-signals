"""Read the workbook produced by the ETL pipeline (IPAI_quarterly_series.xlsx)."""
import re

import pandas as pd

SHEETS = {"Global": r"^03_Cat_Global$", "Residential": r"^04_Cat_Residential$",
          "Land": r"^05_Cat_Land$", "Commercial": r"^06_Cat_Commercial$"}
COLS = {"Price_QoQ": "price change qoq", "Price_YoY": "price change yoy",
        "Trans_QoQ": "transactions change qoq", "Trans_YoY": "transactions change yoy"}
HIST_COLS = ["Quarter", "Year", "Qtr", "Chrono_order", "Category", "Price_QoQ", "Price_YoY", "Trans_QoQ", "Trans_YoY"]


def qkey(label):
    return int(label[3:]) * 4 + int(label[1])


def load_workbook_series(xlsx_path, first_quarter="Q1-2020"):
    """Return (historical fact table, last quarter, messages)."""
    xl = pd.ExcelFile(xlsx_path)
    msgs, frames = [], []
    for cat, pat in SHEETS.items():
        sh = next((n for n in xl.sheet_names if re.match(pat, n)), None)
        if sh is None:
            raise ValueError(f"sheet for category '{cat}' not found in {xlsx_path} (expected: {pat[1:-1]})")
        raw = xl.parse(sh)
        heads = {str(c).strip().lower(): c for c in raw.columns}
        out = pd.DataFrame({"Quarter": raw[heads["quarter"]].astype(str)})
        for target, key in COLS.items():
            col = next((orig for low, orig in heads.items() if low.startswith(key)), None)
            if col is None:
                raise ValueError(f"column '{key}' missing from sheet {sh}: the workbook comes from an older "
                                 f"pipeline version; rerun the extraction (python run_pipeline.py run --rebuild)")
            out[target] = pd.to_numeric(raw[col], errors="coerce")
        out["Category"] = cat
        frames.append(out)
    h = pd.concat(frames, ignore_index=True)
    h = h[h.Quarter.str.match(r"^Q[1-4]-\d{4}$")]
    h["Year"] = h.Quarter.str[3:].astype(int)
    h["Qtr"] = h.Quarter.str[1].astype(int)
    h["Chrono_order"] = h.Year * 4 + h["Qtr"]
    h = h[h.Chrono_order >= qkey(first_quarter)]
    # last quarter = last quarter with a Global price
    g = h[(h.Category == "Global") & h.Price_QoQ.notna()]
    if g.empty:
        raise ValueError("no Global price data in the requested window")
    last = g.sort_values("Chrono_order").Quarter.iloc[-1]
    h = h[h.Chrono_order <= qkey(last)].sort_values(["Chrono_order", "Category"]).reset_index(drop=True)
    for _, r in h[h[list(COLS)].isna().any(axis=1)].iterrows():
        cols = [c for c in COLS if pd.isna(r[c])]
        msgs.append(f"missing value {r.Quarter} / {r.Category}: {', '.join(cols)} (left empty, never imputed)")
    return h[HIST_COLS], last, msgs
