"""Quality checks (publication gates) and series completeness."""
import os
import statistics
from datetime import date

import pandas as pd

from . import quarters as Q


def completeness(S, last_quarter):
    exp = Q.expected_quarters("Q1-2015", last_quarter)
    rows = []

    def add(name, have, note=""):
        miss = [t for t in exp if t not in have]
        rows.append({"series": name, "quarters_expected": len(exp), "quarters_present": len(exp) - len(miss),
                     "completeness_pct": round(100 * (len(exp) - len(miss)) / len(exp), 1),
                     "missing": ", ".join(miss), "note": note})

    T = S["tables"]
    add("national prices (national table)",
        {t for t in exp if T.get(t, {}).get("price_qoq", {}).get("Global") is not None})
    add("national transactions (chart)", set(S["nat"]))
    nrev = sum(1 for e in S["nat"].values() if e[1].startswith("revised"))
    rows[-1]["note"] = f"{nrev} revised value(s) (gap-filled)"
    for c, d in S["city"].items():
        add(f"transactions {c} (chart)", set(d))
        rows[-1]["note"] = f"{sum(1 for e in d.values() if e[1].startswith('revised'))} revised value(s)"
    from charts import ALL_CITIES
    for c in ALL_CITIES:
        add(f"{c}: price % (ten-city table)",
            {t for t in exp if T.get(t, {}).get("cities10", {}).get(c, {}).get("price_qoq") is not None})
        add(f"{c}: transactions % (ten-city table)",
            {t for t in exp if T.get(t, {}).get("cities10", {}).get(c, {}).get("trans_qoq") is not None},
            "column absent from older bulletins (e.g. Q3-2015)")
    return rows


def run_checks(S, long_df, cfg, rl, state, prev_long_path, today=None):
    qc = cfg["quality"]
    if not S["tables"]:
        rl.anomaly("ERROR", "no_data", "-", "no usable bulletin")
        return
    last = max(S["tables"], key=Q.qidx)
    exp_last = Q.latest_completed_quarter(today or date.today())
    # 1) is the latest bulletin present?
    if last != exp_last and Q.qidx(exp_last) > Q.qidx(last):
        rl.anomaly("WARN", "publication_delay", exp_last,
                   f"latest archived bulletin = {last}; latest completed quarter = {exp_last}")
    gaps = [t for t in Q.expected_quarters(cfg["schedule"]["first_quarter"], last) if t not in S["tables"]]
    if gaps:
        rl.anomaly("WARN", "bulletin_missing", f"{len(gaps)} quarter(s)",
                   "no PDF archived for: " + ", ".join(gaps) +
                   " (prices and % tables empty; transaction counts gap-filled from revisions where possible)")
    # 2) is the latest bulletin complete?
    b = S["tables"][last]
    for k in ("price_qoq", "price_yoy", "trans_pct_qoq"):
        if len(b.get(k, {})) < 4:
            rl.anomaly("ERROR", "national_table_incomplete", last, f"{k}: {len(b.get(k, {}))}/4 categories")
    if len(b.get("cities10", {})) < 10:
        rl.anomaly("ERROR", "city_table_incomplete", last, f"{len(b.get('cities10', {}))}/10 cities")
    if last not in S["nat"] or S["nat"][last][1] != "published":
        rl.anomaly("ERROR", "national_transactions_latest_quarter", last,
                   "latest quarter's value not read in its own bulletin")
    # 2b) scale cross-check: latest vs previous bulletin on the quarters both show. This catches a
    #     wrong calibration of the latest chart, which the internal check cannot see.
    prim = S.get("primary", {})
    prev_q = Q.from_idx(Q.qidx(last) - 1)
    if last in prim and prev_q in prim:
        wa, wb = prim[last].get("nat_window", {}), prim[prev_q].get("nat_window", {})
        ratios = [sum(wa[o]) / sum(wb[o + 1]) for o in range(-12, 0)
                  if o in wa and (o + 1) in wb and sum(wb[o + 1])]
        if len(ratios) >= 4:
            med = statistics.median(ratios)
            if abs(med - 1) > 0.03:
                rl.anomaly("ERROR", "suspect_chart_scale", last,
                           f"national transactions: median ratio vs bulletin {prev_q} = {med:.3f} (expected about 1)")
            else:
                rl.step("3-quality", "scale cross-check vs previous bulletin", "OK", f"median ratio {med:.3f}")
    # 3) value ranges
    if long_df is not None and len(long_df):
        p = long_df[(long_df.indicator == "price_change_qoq_pct") & (long_df.value.abs() > qc["max_abs_price_qoq_pct"])]
        for _, r in p.iterrows():
            rl.anomaly("WARN", "unusual_value", f"{r.subseries} {r.quarter}",
                       f"price QoQ = {r.value}% (> {qc['max_abs_price_qoq_pct']}%)")
        t = long_df[(long_df.indicator == "transactions_change_qoq_pct")
                    & (long_df.value.abs() > qc["max_abs_trans_qoq_pct"])]
        for _, r in t.iterrows():
            rl.anomaly("INFO", "unusual_value", f"{r.subseries} {r.quarter}",
                       f"transactions QoQ = {r.value}% (> {qc['max_abs_trans_qoq_pct']}%)")
    # 4) historical drift between two runs (published values only)
    if prev_long_path and os.path.exists(prev_long_path) and long_df is not None:
        prev = pd.read_csv(prev_long_path)
        if "value_source" in prev.columns:
            keys = ["series", "subseries", "quarter", "indicator"]
            m = long_df.merge(prev[keys + ["value", "value_source"]], on=keys, suffixes=("", "_prev"))
            m = m[(m.value_source == "published") & (m.value_source_prev == "published")]
            tol = qc["historical_change_tolerance_pct"]
            for _, r in m.iterrows():
                den = max(abs(r.value_prev), 1e-9)
                same = abs(r.value - r.value_prev) <= (tol / 100 * den if r.unit == "count" else 1e-9)
                if not same:
                    rl.anomaly("WARN", "historical_value_changed", f"{r.subseries} {r.quarter} {r.indicator}",
                               f"{r.value_prev} -> {r.value}")
    rl.step("3-quality", "quality checks", "OK",
            f"{sum(a['severity'] == 'ERROR' for a in rl.anomalies)} error(s), "
            f"{sum(a['severity'] == 'WARN' for a in rl.anomalies)} warning(s)")
