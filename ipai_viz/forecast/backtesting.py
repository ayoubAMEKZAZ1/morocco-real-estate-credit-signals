"""
backtesting.py
--------------
Honest out-of-sample validation of the models by walk-forward backtesting.

At each origin k the model is trained ONLY on data before k (no look-ahead), and its prediction is
compared with the value actually published. This is the only way to measure the error a forecaster
would really have made, quarter after quarter.

Two naive benchmarks are mandatory (a model that cannot beat them adds nothing):
    - persistence   : predict the previous quarter's value
    - seasonal mean : predict the historical mean for that quarter position (Q1/Q2/Q3/Q4),
                      using only the training data available at that date

Two main functions:
    - compare_models_single_step: compares the 5 specifications (M1-M5) and the 2 benchmarks on
      one-step-ahead predictions, to select the best model per series.
    - multihorizon_backtest: for an already selected model, measures the error 1, 2, 3... H quarters
      ahead, to calibrate uncertainty bands that widen with the horizon.
"""

import numpy as np
import pandas as pd

from models import CANDIDATE_MODELS, ModelSpec

MIN_TRAIN_DEFAULT = 14  # minimum training quarters before the first test prediction


def _rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def _mae(a, b):
    return float(np.mean(np.abs(np.asarray(a) - np.asarray(b))))


def _baseline_seasonal_mean(y, Q, min_train):
    n = len(y)
    preds, actuals = [], []
    for k in range(min_train, n):
        same_q = [y[t] for t in range(0, k) if Q[t] == Q[k]]
        preds.append(np.mean(same_q) if same_q else np.nan)
        actuals.append(y[k])
    return np.array(preds), np.array(actuals)


def _baseline_persistence(y, min_train):
    n = len(y)
    preds = [y[k - 1] for k in range(min_train, n)]
    actuals = [y[k] for k in range(min_train, n)]
    return np.array(preds), np.array(actuals)


def _walk_forward_single_step(spec: ModelSpec, y, trend, Q, min_train):
    n = len(y)
    preds, actuals = [], []
    for k in range(min_train, n):
        train_start = 1 if spec.use_ar1 else 0
        train_idx = list(range(train_start, k))
        try:
            model = spec.fit(train_idx, y, trend, Q)
        except ValueError:
            continue
        preds.append(spec.predict_one(model, k, y, trend, Q))
        actuals.append(y[k])
    return np.array(preds), np.array(actuals)


def compare_models_single_step(y: np.ndarray, Q: np.ndarray, min_train: int = MIN_TRAIN_DEFAULT) -> dict:
    """
    Compare the 5 candidate models and the 2 naive benchmarks on one-step-ahead predictions.

    Return a dict with the RMSE of each candidate and benchmark, and the name of the best model
    (lowest RMSE).
    """
    n = len(y)
    trend = np.arange(n)

    ps, act_s = _baseline_seasonal_mean(y, Q, min_train)
    pp, act_p = _baseline_persistence(y, min_train)
    out = {
        "rmse_persistence": _rmse(act_p, pp),
        "rmse_seasonal_mean": _rmse(act_s, ps),
    }

    best_name, best_rmse = None, np.inf
    for key, spec in CANDIDATE_MODELS.items():
        preds, actuals = _walk_forward_single_step(spec, y, trend, Q, min_train)
        r = _rmse(actuals, preds)
        out[f"rmse_{spec.name}"] = r
        if r < best_rmse:
            best_rmse, best_name = r, key
    out["best_model"] = best_name
    out["rmse_best_model"] = best_rmse
    out["beats_seasonal_mean"] = best_rmse < out["rmse_seasonal_mean"]
    out["beats_persistence"] = best_rmse < out["rmse_persistence"]
    return out


def _h_step_forecast_from_origin(spec: ModelSpec, y, Q, origin: int, horizon: int):
    """Forecast origin+1 to origin+horizon using ONLY data up to origin."""
    train_idx = list(range(1 if spec.use_ar1 else 0, origin + 1))
    trend = np.arange(len(y))
    model = spec.fit(train_idx, y, trend, Q)
    preds = []
    last_val = y[origin]
    for h in range(1, horizon + 1):
        k = origin + h
        if spec.use_ar1:
            # feed back the last prediction (the true value is unknown at this horizon)
            feats = [1.0 if Q[k] == p else 0.0 for p in [1, 2, 3, 4]] + [last_val]
            pred = float(model.predict(np.array([feats]))[0])
            last_val = pred
        else:
            pred = spec.predict_one(model, k, y, trend, Q)
        preds.append(pred)
    return preds


def multihorizon_backtest(y: np.ndarray, Q: np.ndarray, model_key: str,
                           horizon_max: int = 6, min_train: int = MIN_TRAIN_DEFAULT) -> pd.DataFrame:
    """
    Measure the forecast error (RMSE, MAE) at each horizon 1..horizon_max for the selected
    model `model_key` (e.g. "M1").

    Return one row per horizon: RMSE, MAE and the number of test origins available (longer
    horizons have fewer valid origins; this is reported, not hidden).
    """
    spec = CANDIDATE_MODELS[model_key]
    n = len(y)
    errors_by_h = {h: [] for h in range(1, horizon_max + 1)}
    for origin in range(min_train - 1, n - 1):
        max_h = min(horizon_max, n - 1 - origin)
        if max_h < 1:
            continue
        preds = _h_step_forecast_from_origin(spec, y, Q, origin, max_h)
        for h in range(1, max_h + 1):
            errors_by_h[h].append(y[origin + h] - preds[h - 1])

    rows = []
    for h in range(1, horizon_max + 1):
        errs = np.array(errors_by_h[h])
        if len(errs) == 0:
            continue
        rows.append({"horizon_h": h, "n_origins": len(errs),
                      "rmse_h": _rmse(errs, np.zeros_like(errs)),
                      "mae_h": _mae(errs, np.zeros_like(errs))})
    return pd.DataFrame(rows)


def monotonic_rmse_floor(horizon_df: pd.DataFrame) -> dict[int, float]:
    """
    Apply a monotonic floor to RMSE by horizon: uncertainty must NEVER appear to shrink with the
    horizon, even when a small sample of origins (common at horizons 5-6) suggests it.

    Return {horizon: adjusted_rmse}.
    """
    floor = 0.0
    out = {}
    for _, row in horizon_df.sort_values("horizon_h").iterrows():
        floor = max(floor, row["rmse_h"])
        out[int(row["horizon_h"])] = floor
    return out
