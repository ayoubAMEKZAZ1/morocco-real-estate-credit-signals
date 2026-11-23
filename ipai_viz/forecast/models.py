"""
models.py
---------
Candidate model specifications for forecasting the quarterly IPAI rates.

Deliberate choice: robust linear regression (HuberRegressor), NOT a black box. Every coefficient
stays interpretable (average seasonal effect, trend effect, dependence on the previous quarter).
The implementation uses scikit-learn; the specification (least squares / Huber M-estimator) is the
same one statsmodels would fit.

Five specifications are compared, and the "best" model per series is chosen ONLY on out-of-sample
backtesting results (see backtesting.py), never on prior judgement:

    M1  seasonal only                 : y_t ~ dummies(Q1..Q4)
    M2  seasonal + trend              : y_t ~ dummies(Q1..Q4) + trend
    M3  seasonal + AR(1)              : y_t ~ dummies(Q1..Q4) + y_(t-1)
    M4  seasonal + trend + AR(1)      : y_t ~ dummies(Q1..Q4) + trend + y_(t-1)
    M5  seasonal only, plain OLS (not robust): control variant of M1

Empirical finding from the project's backtest: a global linear trend is NOT a good predictor for
these series (the market moves in cycles, not monotonically). M1 or M3 wins depending on the series.
"""

from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import HuberRegressor, LinearRegression

QUARTER_POSITIONS = [1, 2, 3, 4]


def _dummies(q: int) -> list[float]:
    return [1.0 if q == pos else 0.0 for pos in QUARTER_POSITIONS]


@dataclass
class ModelSpec:
    name: str
    use_trend: bool
    use_ar1: bool
    regressor: str  # "huber" or "ols"

    def make_regressor(self):
        if self.regressor == "huber":
            return HuberRegressor(max_iter=500)
        return LinearRegression()

    def build_features(self, t: int, y: np.ndarray, trend: np.ndarray, Q: np.ndarray) -> list[float]:
        row = _dummies(Q[t])
        if self.use_trend:
            row = [trend[t]] + row
        if self.use_ar1:
            row = row + [y[t - 1]]
        return row

    def build_design_matrix(self, idx_range, y: np.ndarray, trend: np.ndarray, Q: np.ndarray):
        rows, ys = [], []
        for t in idx_range:
            if self.use_ar1 and t < 1:
                continue
            rows.append(self.build_features(t, y, trend, Q))
            ys.append(y[t])
        return np.array(rows), np.array(ys)

    def fit(self, train_idx, y: np.ndarray, trend: np.ndarray, Q: np.ndarray):
        X, yv = self.build_design_matrix(train_idx, y, trend, Q)
        if len(yv) < 5:
            raise ValueError(f"[{self.name}] not enough training observations ({len(yv)})")
        model = self.make_regressor()
        model.fit(X, yv)
        return model

    def predict_one(self, model, t: int, y: np.ndarray, trend: np.ndarray, Q: np.ndarray) -> float:
        X_t = np.array([self.build_features(t, y, trend, Q)])
        return float(model.predict(X_t)[0])


CANDIDATE_MODELS: dict[str, ModelSpec] = {
    "M1": ModelSpec("M1_seasonal_only", use_trend=False, use_ar1=False, regressor="huber"),
    "M2": ModelSpec("M2_seasonal_trend", use_trend=True, use_ar1=False, regressor="huber"),
    "M3": ModelSpec("M3_seasonal_AR1", use_trend=False, use_ar1=True, regressor="huber"),
    "M4": ModelSpec("M4_seasonal_trend_AR1", use_trend=True, use_ar1=True, regressor="huber"),
    "M5": ModelSpec("M5_seasonal_only_OLS", use_trend=False, use_ar1=False, regressor="ols"),
}

# Winning model per series from the project's comparative backtest (September 2026).
# RE-RUN the comparison (backtesting.compare_models_single_step) when new data are added rather
# than assuming this choice stays valid forever. The dashboards' validation panel re-checks every
# run that each winner still beats both naive benchmarks.
WINNING_MODEL = {
    ("Global", "price"): "M1",
    ("Global", "transactions"): "M1",
    ("Residential", "price"): "M1",
    ("Residential", "transactions"): "M1",
    ("Land", "price"): "M3",
    ("Land", "transactions"): "M1",
    ("Commercial", "price"): "M3",
    ("Commercial", "transactions"): "M1",
}
