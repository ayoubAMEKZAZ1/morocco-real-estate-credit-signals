"""Build one quarterly panel from the three public sources.

IPAI (Bank Al-Maghrib / ANCFCC)  : price and transaction changes, % QoQ and % YoY, by asset category
BAM monetary statistics          : outstanding real-estate credit at each quarter end, MAD million
Cement deliveries (APC)          : cumulative deliveries at each quarter end, tonnes

Every derived column uses only values available at that quarter, so the panel can be used for
lead/lag analysis without look-ahead.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

CREDIT_SERIES = ["real_estate_total", "housing", "property_developers"]


def load_ipai() -> pd.DataFrame:
    """Wide IPAI table: one row per quarter, columns like price_yoy_Global, transactions_qoq_Land."""
    L = pd.read_csv(DATA / "ipai" / "ipai_official_rates_2020Q1_2026Q2.csv")
    L["col"] = L.metric + "_" + L.change + "_" + L.category
    W = L.pivot(index="quarter", columns="col", values="value_pct")
    W.index = pd.PeriodIndex(W.index, freq="Q")
    return W.sort_index()


def load_credit() -> pd.DataFrame:
    """Quarter-end outstanding credit (latest published vintage), plus YoY and QoQ growth in %."""
    C = pd.read_csv(DATA / "external" / "bam_real_estate_credit_monthly.csv")
    C["month"] = pd.PeriodIndex(C.month, freq="M")
    C = C[C.month.dt.month.isin([3, 6, 9, 12])]
    W = C.pivot(index="month", columns="series", values="outstanding_mad_million")
    W.index = W.index.asfreq("Q")
    out = pd.DataFrame(index=W.index)
    for s in CREDIT_SERIES:
        out[f"credit_{s}_mad_m"] = W[s]
        out[f"credit_{s}_yoy"] = 100 * W[s].pct_change(4)
        out[f"credit_{s}_qoq"] = 100 * W[s].pct_change(1)
    out["developer_share_of_re_credit"] = 100 * W.property_developers / W.real_estate_total
    return out


def load_cement() -> pd.DataFrame:
    """Quarterly cement deliveries from year-to-date cumulative figures, plus YoY growth in %."""
    K = pd.read_csv(DATA / "external" / "cement_deliveries_cumulative.csv")
    K["quarter"] = pd.PeriodIndex.from_fields(year=K.year, quarter=K.through_month // 3, freq="Q")
    K = K.sort_values(["year", "through_month"])
    K["quarterly_tonnes"] = K.groupby("year").cumulative_tonnes.diff().fillna(K.cumulative_tonnes)
    K = K.set_index("quarter")
    out = pd.DataFrame(index=K.index)
    out["cement_quarter_tonnes"] = K.quarterly_tonnes
    out["cement_ytd_tonnes"] = K.cumulative_tonnes
    out["cement_quarter_yoy"] = 100 * K.quarterly_tonnes.pct_change(4)
    out["cement_ytd_yoy"] = 100 * K.cumulative_tonnes.pct_change(4)
    out["cement_rounded_input"] = (K.precision == "rounded") | (K.precision.shift(1) == "rounded")
    return out


def build_panel() -> pd.DataFrame:
    P = load_ipai().join(load_credit(), how="outer").join(load_cement(), how="outer")
    # Developer margin proxy: land prices rising faster than finished residential prices
    # squeeze developer margins; the spread is the land YoY change minus the residential YoY change.
    P["developer_margin_proxy"] = P["price_yoy_Residential"] - P["price_yoy_Land"]
    P["ipai_perimeter_break"] = P.index >= pd.Period("2025Q1", "Q")   # coverage widened to 83 land registries
    P.index.name = "quarter"
    return P


if __name__ == "__main__":
    P = build_panel()
    print(P.loc["2020Q1":, ["price_yoy_Global", "transactions_yoy_Global", "credit_property_developers_yoy",
                            "cement_quarter_yoy", "developer_margin_proxy"]].round(2).to_string())
