"""Adapter around the validated forecasting code (vendored in forecast/).

This module does not change the forecasting method. It only:
(1) builds the input from the series read in the pipeline workbook,
(2) runs the forecasts for the 8 series (4 categories x prices/transactions),
(3) recomputes the validation summary on every run (winning model vs 2 naive benchmarks).
No missing value is imputed: if a series is incomplete, its forecasts are skipped.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "forecast"))
from models import WINNING_MODEL, CANDIDATE_MODELS  # noqa: E402
from forecast import forecast_series  # noqa: E402
from backtesting import (_walk_forward_single_step, _baseline_seasonal_mean,  # noqa: E402
                         _baseline_persistence, _rmse, MIN_TRAIN_DEFAULT)

CATS = ["Global", "Residential", "Land", "Commercial"]
METRICS = {"price": "Price_QoQ", "transactions": "Trans_QoQ"}
FORECAST_COLS = ["Quarter", "Year", "Qtr", "Chrono_order", "Category", "Metric", "Horizon_h", "Model",
                 "Central", "Pessimistic", "Optimistic", "RMSE_horizon", "N_origins_horizon"]


def next_quarters(last_label, n):
    q, y = int(last_label[1]), int(last_label[3:])
    out = []
    for _ in range(n):
        q += 1
        if q == 5:
            q, y = 1, y + 1
        out.append((f"Q{q}-{y}", q))
    return out


def run_forecasts(hist, last_label, horizon=6):
    """hist: historical fact table (Quarter, Qtr, Chrono_order, Category, Price_QoQ, Trans_QoQ...).
    Return (forecast fact table, messages)."""
    msgs, frames = [], []
    fut = next_quarters(last_label, horizon)
    fq, fQ = [a for a, _ in fut], [b for _, b in fut]
    for cat in CATS:
        d = hist[hist.Category == cat].sort_values("Chrono_order")
        for metric, col in METRICS.items():
            y = d[col].astype(float).values
            Q = d["Qtr"].astype(int).values
            if len(y) < MIN_TRAIN_DEFAULT + 4:
                msgs.append(f"forecast {cat}/{metric} skipped: only {len(y)} quarters")
                continue
            if np.isnan(y).any():
                bad = d.loc[d[col].isna(), "Quarter"].tolist()
                msgs.append(f"forecast {cat}/{metric} skipped: missing values ({', '.join(bad)}); no imputation")
                continue
            res = forecast_series(y, Q, WINNING_MODEL[(cat, metric)], fq, fQ, cat, metric)
            frames.append(pd.DataFrame([r.__dict__ for r in res]))
    if not frames:
        return pd.DataFrame(columns=FORECAST_COLS), msgs
    f = pd.concat(frames, ignore_index=True)
    out = pd.DataFrame({"Quarter": f.quarter, "Year": f.quarter.str[3:].astype(int),
                        "Qtr": f.quarter.str[1].astype(int)})
    out["Chrono_order"] = out.Year * 4 + out["Qtr"]
    out["Category"] = f.category
    out["Metric"] = f.metric
    out["Horizon_h"] = f.horizon_h
    out["Model"] = f.model
    out["Central"], out["Pessimistic"], out["Optimistic"] = f.central, f.pessimistic, f.optimistic
    out["RMSE_horizon"], out["N_origins_horizon"] = f.rmse_horizon, f.n_origins_horizon
    return out[FORECAST_COLS], msgs


def validation_summary(hist):
    """For each of the 8 series: does the winning model beat persistence AND the seasonal mean
    (walk-forward, one step ahead)? Return (n_ok, n_total, details list[dict])."""
    rows = []
    for cat in CATS:
        d = hist[hist.Category == cat].sort_values("Chrono_order")
        for metric, col in METRICS.items():
            y = d[col].astype(float).values
            Q = d["Qtr"].astype(int).values
            if len(y) < MIN_TRAIN_DEFAULT + 4 or np.isnan(y).any():
                continue
            spec = CANDIDATE_MODELS[WINNING_MODEL[(cat, metric)]]
            n = len(y)
            p, a = _walk_forward_single_step(spec, y, np.arange(n), Q, MIN_TRAIN_DEFAULT)
            ps, as_ = _baseline_seasonal_mean(y, Q, MIN_TRAIN_DEFAULT)
            pp, ap = _baseline_persistence(y, MIN_TRAIN_DEFAULT)
            r, rs, rp = _rmse(a, p), _rmse(as_, ps), _rmse(ap, pp)
            rows.append({"category": cat, "metric": metric, "rmse_model": r, "rmse_seasonal_mean": rs,
                         "rmse_persistence": rp, "beats_both": r < rs and r < rp})
    return sum(r["beats_both"] for r in rows), len(rows), rows
