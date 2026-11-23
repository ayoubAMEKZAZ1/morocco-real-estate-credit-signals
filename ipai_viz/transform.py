"""Derived measures for the dashboards (equivalent of the Tableau calculated fields)."""
import numpy as np
import pandas as pd

CATS = ["Global", "Residential", "Land", "Commercial"]


def dim_quarter(hist, fprev):
    d = hist[["Quarter", "Year", "Qtr", "Chrono_order"]].drop_duplicates().assign(Period_type="Historical")
    if fprev is not None and len(fprev):
        f = fprev[["Quarter", "Year", "Qtr", "Chrono_order"]].drop_duplicates().assign(Period_type="Forecast")
        d = pd.concat([d, f], ignore_index=True)
    return d.sort_values("Chrono_order").reset_index(drop=True)


def global_combo(hist, cfg):
    """Bars = Price_QoQ; line = Trans_QoQ (axes not synchronised)."""
    if cfg["strict_twb_mode"]:  # the .twb averages the 4 categories (no Category filter)
        g = hist.groupby("Quarter", sort=False)[["Price_QoQ", "Trans_QoQ"]].mean()
        note = "average of the 4 categories (strict .twb reproduction)"
    else:
        g = hist[hist.Category == "Global"].set_index("Quarter")[["Price_QoQ", "Trans_QoQ"]]
        note = "Global category"
    return g.reset_index(), note


def profile(hist, category):
    return hist[hist.Category == category][["Quarter", "Price_QoQ", "Trans_QoQ"]].reset_index(drop=True)


def yoy_wide(hist, col):
    return hist.pivot(index="Quarter", columns="Category", values=col).reindex(
        hist.drop_duplicates("Quarter").sort_values("Chrono_order").Quarter)[CATS]


def margin(hist, cfg):
    """YoY price spreads: Land minus Residential and Land minus Commercial (developer margin proxy)."""
    w = yoy_wide(hist, "Price_YoY")
    out = pd.DataFrame({"Land − Residential": w["Land"] - w["Residential"],
                        "Land − Commercial": w["Land"] - w["Commercial"]})
    if cfg["strict_twb_mode"]:
        out = out * 4  # SUM over 4 rows (one per category) in the .twb
    return out.reset_index()


def retro(hist, col):
    """Compound annual growth by (year, category): (exp(sum ln(1 + q/100)) - 1) x 100.
    Return a DataFrame with Year, Category, value, n_quarters (quarters available), complete."""
    rows = []
    for (a, c), d in hist.groupby(["Year", "Category"]):
        v = d[col].dropna()
        if v.empty:
            continue
        rows.append({"Year": a, "Category": c, "value": (np.exp(np.log1p(v / 100).sum()) - 1) * 100,
                     "n_quarters": len(v), "complete": len(v) == 4 and len(d) == 4})
    return pd.DataFrame(rows)


def seasonality(hist, last_label, cfg):
    """Average seasonal profile by quarter (Q1..Q4) over complete years (up to the last complete one)."""
    ly, lt = int(last_label[3:]), int(last_label[1])
    cutoff = ly if lt == 4 else ly - 1
    d = hist[hist.Year <= cutoff]
    if cfg["strict_twb_mode"]:
        s = d.groupby("Qtr")[["Price_QoQ", "Trans_QoQ"]].sum()
        note = f"sum over 4 categories x years up to {cutoff} (strict .twb reproduction)"
    else:
        cat = cfg["seasonality_category"]
        s = d[d.Category == cat].groupby("Qtr")[["Price_QoQ", "Trans_QoQ"]].mean() if cat else \
            d.groupby("Qtr")[["Price_QoQ", "Trans_QoQ"]].mean()
        note = f"average, {cat or 'all categories'}, years up to {cutoff}"
    return s.reset_index(), note, cutoff
