"""Lead/lag analysis and early-warning flags for developer credit risk.

Questions answered:
1. Do cement deliveries lead real-estate activity (IPAI transactions) or developer credit?
2. Does credit to developers move with prices and transaction volumes?
3. Which indicators are unusually far from their own history in the latest quarter?

With about 26 quarters, correlations are indicative, not causal. Every result is reported with its
sample size and the rough 95% band for a zero correlation (plus or minus 2 divided by sqrt(n)).
Spearman correlations are reported alongside Pearson because the 2020-2021 lockdown and rebound
produce extreme values (transactions +220% YoY in 2021Q2).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PAIRS = [
    # (leading indicator, target, plain-language reading)
    ("cement_quarter_yoy", "transactions_yoy_Global", "Cement deliveries vs property transactions"),
    ("cement_quarter_yoy", "price_yoy_Global", "Cement deliveries vs property prices"),
    ("cement_quarter_yoy", "credit_property_developers_yoy", "Cement deliveries vs credit to developers"),
    ("credit_property_developers_yoy", "transactions_yoy_Global", "Credit to developers vs transactions"),
    ("credit_housing_yoy", "transactions_yoy_Residential", "Housing loans vs residential transactions"),
    ("credit_housing_yoy", "price_yoy_Residential", "Housing loans vs residential prices"),
]

SIGNAL_RULES = [
    # (column, label, which direction is a risk for developer portfolios)
    ("cement_quarter_yoy", "Cement deliveries, quarter YoY %", "low"),
    ("cement_ytd_yoy", "Cement deliveries, year-to-date YoY %", "low"),
    ("transactions_yoy_Global", "IPAI transactions, YoY %", "low"),
    ("price_yoy_Global", "IPAI prices, YoY %", "low"),
    ("credit_property_developers_yoy", "Credit to developers, YoY %", "high"),
    ("developer_share_of_re_credit", "Developers' share of real-estate credit, %", "high"),
    ("developer_margin_proxy", "Developer margin proxy (residential minus land price YoY), pp", "low"),
]


def lagged_correlations(P: pd.DataFrame, start="2020Q1", end=None, max_lag=4) -> pd.DataFrame:
    """corr(X shifted by k quarters, Y): k > 0 means X leads Y by k quarters."""
    D = P.loc[start:end]
    rows = []
    for x, y, label in PAIRS:
        for k in range(0, max_lag + 1):
            pair = pd.concat([D[x].shift(k), D[y]], axis=1).dropna()
            n = len(pair)
            if n < 8:
                continue
            rows.append(dict(pair=label, leader=x, target=y, lead_quarters=k, n=n,
                             pearson=pair.corr().iloc[0, 1],
                             spearman=pair.corr(method="spearman").iloc[0, 1],
                             zero_band=2 / np.sqrt(n)))
    R = pd.DataFrame(rows)
    R["notable"] = (R.pearson.abs() > R.zero_band) & (R.spearman.abs() > R.zero_band)
    return R


def signal_table(P: pd.DataFrame, history_start="2022Q1") -> pd.DataFrame:
    """Z-score of the latest available value of each indicator against its own history.

    History starts in 2022Q1 by default so the 2020-2021 lockdown swings do not inflate the
    standard deviation and hide genuine stress.
    """
    rows = []
    for col, label, risk_dir in SIGNAL_RULES:
        s = P[col].dropna()
        last_q = s.index[-1]
        hist = s.loc[history_start:last_q - 1]
        z = (s.iloc[-1] - hist.mean()) / hist.std(ddof=1)
        risk = z <= -1 if risk_dir == "low" else z >= 1
        strong = z <= -2 if risk_dir == "low" else z >= 2
        rows.append(dict(indicator=label, quarter=str(last_q), value=s.iloc[-1], history_mean=hist.mean(),
                         history_sd=hist.std(ddof=1), z_score=z,
                         flag="ALERT" if strong else ("WATCH" if risk else "normal")))
    return pd.DataFrame(rows)


def quarter_flags(P: pd.DataFrame, col: str, risk_dir: str, history_start="2022Q1") -> pd.DataFrame:
    """Expanding-window z-score for each quarter (no look-ahead): which past quarters would have flagged."""
    s = P[col].dropna()
    out = []
    for q in s.loc[history_start:].index:
        hist = s.loc[history_start:q - 1]
        if len(hist) < 6:
            continue
        z = (s[q] - hist.mean()) / hist.std(ddof=1)
        out.append(dict(quarter=str(q), value=s[q], z_score=z,
                        flag=(z <= -1) if risk_dir == "low" else (z >= 1)))
    return pd.DataFrame(out)
