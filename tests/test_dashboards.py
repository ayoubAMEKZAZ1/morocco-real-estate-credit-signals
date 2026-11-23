import os
import sys
import tempfile

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ipai_viz.build import build  # noqa: E402

WORKBOOK = os.path.join(ROOT, "data", "ipai", "IPAI_quarterly_series.xlsx")


def test_dashboards_and_forecasts():
    out = tempfile.mkdtemp()
    r = build(WORKBOOK, out)
    assert (r["first"], r["last"]) == ("Q1-2020", "Q2-2026")
    assert r["validation"][1] == 8                       # all 8 series validated
    for name in ("1_overview", "4_credit_product_profile", "7_model_and_forecast"):
        assert os.path.exists(os.path.join(out, "dashboards", f"{name}.png"))
    f = pd.read_csv(os.path.join(out, "tableau_csv", "fact_forecasts.csv"), encoding="utf-8-sig")
    assert len(f) == 48                                  # 8 series x 6 quarters
    g = f[(f.Category == "Global") & (f.Metric == "price") & (f.Quarter == "Q3-2026")].iloc[0]
    assert (g.Central, g.Pessimistic, g.Optimistic) == (0.65, -0.39, 1.69)   # same as the September 2026 run
