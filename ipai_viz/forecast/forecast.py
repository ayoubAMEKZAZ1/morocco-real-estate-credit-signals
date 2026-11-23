"""
forecast.py
-----------
Final forecasts: refit each series' winning model on ALL available data (no holdout, since the
backtest has already validated the method), then project H quarters ahead with a
[pessimistic, optimistic] band calibrated on the real backtest error at each horizon
(see backtesting.monotonic_rmse_floor).

Convention: optimistic = central + RMSE_h, pessimistic = central - RMSE_h (consistent for prices
AND transactions: a higher number means a more active market).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from models import CANDIDATE_MODELS, ModelSpec
from backtesting import multihorizon_backtest, monotonic_rmse_floor, MIN_TRAIN_DEFAULT


@dataclass
class ForecastResult:
    category: str
    metric: str
    quarter: str
    horizon_h: int
    model: str
    central: float
    pessimistic: float
    optimistic: float
    rmse_horizon: float
    n_origins_horizon: int


def _fit_full(spec: ModelSpec, y: np.ndarray, Q: np.ndarray):
    n = len(y)
    trend = np.arange(n)
    train_idx = list(range(1 if spec.use_ar1 else 0, n))
    return spec.fit(train_idx, y, trend, Q), trend


def forecast_series(y: np.ndarray, Q_hist: np.ndarray, model_key: str,
                    future_quarters: list[str], future_Q: list[int],
                    category: str, metric: str,
                    horizon_max: int = 6, min_train: int = MIN_TRAIN_DEFAULT) -> list[ForecastResult]:
    """Forecast `future_quarters` (chronological, increasing horizon) for one (category, metric)
    series with its winning model `model_key`."""
    spec = CANDIDATE_MODELS[model_key]

    # 1) uncertainty band per horizon, calibrated on the real backtest (monotonic floor)
    hdf = multihorizon_backtest(y, Q_hist, model_key, horizon_max=horizon_max, min_train=min_train)
    rmse_by_h = monotonic_rmse_floor(hdf)
    n_origins_by_h = hdf.set_index("horizon_h")["n_origins"].to_dict()

    # 2) final refit on all available data
    model, _ = _fit_full(spec, y, Q_hist)

    results = []
    last_val = y[-1]
    for h, (qtxt, qpos) in enumerate(zip(future_quarters, future_Q), start=1):
        feats = [1.0 if qpos == p else 0.0 for p in [1, 2, 3, 4]]
        if spec.use_ar1:
            feats = feats + [last_val]
        pred = float(model.predict(np.array([feats]))[0])
        if spec.use_ar1:
            last_val = pred  # iterate: feed back the prediction, not a real future value

        r = rmse_by_h.get(h, max(rmse_by_h.values()) if rmse_by_h else np.nan)
        results.append(ForecastResult(
            category=category, metric=metric, quarter=qtxt, horizon_h=h,
            model=model_key, central=round(pred, 2),
            pessimistic=round(pred - r, 2), optimistic=round(pred + r, 2),
            rmse_horizon=round(r, 2), n_origins_horizon=int(n_origins_by_h.get(h, 0)),
        ))
    return results


def forecasts_to_dataframe(results: list[ForecastResult]) -> pd.DataFrame:
    return pd.DataFrame([r.__dict__ for r in results])
