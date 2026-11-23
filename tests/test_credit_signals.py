import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from credit_signals.analysis import lagged_correlations, quarter_flags, signal_table  # noqa: E402
from credit_signals.panel import DATA, build_panel, load_cement, load_credit  # noqa: E402


def test_credit_vintages_consistent():
    """Overlapping months published in two bulletins differ only by small official revisions."""
    A = pd.read_csv(DATA / "external" / "bam_real_estate_credit_all_vintages.csv")
    g = A.groupby(["month", "series"]).outstanding_mad_million
    spread = (g.max() - g.min()) / g.min()
    assert spread.max() < 0.03


def test_credit_components_below_total():
    C = load_credit()
    assert (C.credit_housing_mad_m + C.credit_property_developers_mad_m <= C.credit_real_estate_total_mad_m).all()


def test_cement_quarters_sum_to_year():
    K = load_cement()
    full_years = K[K.index.quarter == 4]
    for q in full_years.index:
        year = K[K.index.year == q.year]
        assert abs(year.cement_quarter_tonnes.sum() - K.loc[q, "cement_ytd_tonnes"]) < 1


def test_known_cement_values():
    K = load_cement()
    assert round(K.loc["2026Q1", "cement_quarter_yoy"], 1) == -10.9      # reported -10.95%
    assert round(K.loc["2024Q4", "cement_ytd_yoy"], 1) == 9.4            # reported +9.45%


def test_panel_and_no_lookahead_flags():
    P = build_panel()
    assert {"price_yoy_Global", "credit_property_developers_yoy", "cement_quarter_yoy"} <= set(P.columns)
    F = quarter_flags(P, "cement_quarter_yoy", "low")
    assert F.set_index("quarter").loc["2026Q1", "flag"]


def test_correlations_and_signals_shape():
    P = build_panel()
    R = lagged_correlations(P, start="2022Q1")
    assert (R.n >= 8).all() and R.pearson.between(-1, 1).all()
    T = signal_table(P)
    assert set(T.flag) <= {"normal", "WATCH", "ALERT"}
