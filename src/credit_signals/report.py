"""Charts, CSV outputs and a Markdown report for the credit and cement signals."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .analysis import lagged_correlations, quarter_flags, signal_table  # noqa: E402
from .panel import ROOT, build_panel  # noqa: E402

# Reference palette (categorical slots 1-3, text inks, surface) - see docs/CHART_STYLE.md
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
ALERT = "#e34948"
WATCH = "#ec835a"   # status: serious

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "lines.linewidth": 2,
})


def _qlabels(idx):
    return [str(q) if q.quarter == 1 else "" for q in idx]


def chart_cement_vs_credit(P, path):
    D = P.loc["2020Q1":"2026Q3"]
    x = range(len(D))
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5.6), sharex=True)
    a1.bar(x, D.cement_quarter_yoy, color=[ALERT if v <= -10 else BLUE for v in D.cement_quarter_yoy.fillna(0)],
           width=0.7)
    a1.axhline(0, color=INK2, lw=0.8)
    a1.set_title("Cement deliveries, % change on the same quarter a year earlier (red: fall of 10% or more)")
    i26 = list(D.index).index(pd.Period("2026Q1", "Q"))
    a1.annotate("2026Q1: -10.9%", (i26, -10.9), xytext=(i26, -24), ha="center", color=INK, fontsize=9,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    a2.plot(x, D.credit_property_developers_yoy, color=ORANGE, marker="o", ms=4, label="Loans to property developers")
    a2.plot(x, D.credit_housing_yoy, color=AQUA, marker="o", ms=4, label="Housing loans")
    a2.axhline(0, color=INK2, lw=0.8)
    a2.set_title("Outstanding bank credit, % change year on year")
    a2.legend(frameon=False, loc="lower right")
    a2.set_xticks(list(x))
    a2.set_xticklabels(_qlabels(D.index))
    fig.text(0.01, 0.005, "Sources: APC / Ministry of Housing (cement); Bank Al-Maghrib quarterly bulletins, "
             "Table I-4 (credit).", fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def chart_lead_lag(R, path):
    S = R[R.pair == "Cement deliveries vs credit to developers"]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for k, r, n, b, ok in zip(S.lead_quarters, S.pearson, S.n, S.zero_band, S.notable):
        ax.bar(k, r, color=BLUE if ok else GRID, width=0.55)
        ax.hlines(b, k - 0.34, k + 0.34, color=INK2, lw=1, ls="--")
        ax.text(k, max(r, b) + 0.03, f"{r:.2f}\nn={n}", ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_xticks(S.lead_quarters)
    ax.set_xticklabels([f"{k} q" if k else "same q" for k in S.lead_quarters])
    ax.set_ylim(-0.5, 1.05)
    ax.set_xlabel("Cement deliveries lead credit to developers by")
    ax.set_ylabel("Correlation (Pearson)")
    ax.set_title("Cement leads developer credit (2022Q1-2026Q2)")
    ax.text(-0.45, -0.42, "Dashed line: 95% threshold for that sample size. Blue: above it on both Pearson and Spearman.",
            fontsize=8, color=INK2)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def chart_signals(T, path):
    T = T.iloc[::-1]
    fig, ax = plt.subplots(figsize=(11, 4.2))
    colors = [WATCH if f != "normal" else BLUE for f in T.flag]
    ax.barh(T.indicator, T.z_score, color=colors, height=0.55)
    for v in (-1, 1):
        ax.axvline(v, color=INK2, lw=0.8, ls="--")
    ax.axvline(0, color=INK2, lw=0.8)
    for i, (z, f, q) in enumerate(zip(T.z_score, T.flag, T.quarter)):
        ax.text(z + (0.06 if z >= 0 else -0.06), i, f"{z:+.2f}  {f.upper() if f != 'normal' else ''} ({q})",
                va="center", ha="left" if z >= 0 else "right", fontsize=8, color=INK)
    ax.set_xlim(-2.6, 3.4)
    ax.set_xlabel("z-score of the latest quarter against its 2022+ history (dashed: plus or minus 1)")
    fig.suptitle("Early-warning dashboard: latest reading of each indicator", x=0.01, ha="left",
                 fontweight="bold", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def run(out_dir: Path | None = None) -> dict:
    out = Path(out_dir or ROOT / "outputs")
    out.mkdir(parents=True, exist_ok=True)
    P = build_panel()
    R_full = lagged_correlations(P, start="2020Q1")
    R_post = lagged_correlations(P, start="2022Q1")
    T = signal_table(P)
    F = quarter_flags(P, "cement_quarter_yoy", "low")
    P.to_csv(out / "quarterly_panel.csv")
    pd.concat([R_full.assign(sample="2020Q1-2026Q2"), R_post.assign(sample="2022Q1-2026Q2")]).to_csv(
        out / "lead_lag_correlations.csv", index=False)
    T.to_csv(out / "early_warning_signals.csv", index=False)
    chart_cement_vs_credit(P, out / "fig1_cement_vs_credit.png")
    chart_lead_lag(R_post, out / "fig2_cement_leads_developer_credit.png")
    chart_signals(T, out / "fig3_early_warning_signals.png")
    _write_report(P, R_full, R_post, T, F, out / "credit_signals_report.md")
    return dict(panel=P, corr_full=R_full, corr_post=R_post, signals=T, cement_flags=F)


def _fmt_corr(R):
    S = R.sort_values(["pair", "lead_quarters"])
    lines = ["| Pair | Lead (quarters) | n | Pearson | Spearman | Distinguishable from zero |", "|---|---|---|---|---|---|"]
    for r in S.itertuples():
        lines.append(f"| {r.pair} | {r.lead_quarters} | {r.n} | {r.pearson:+.2f} | {r.spearman:+.2f} | "
                     f"{'yes' if r.notable else 'no'} |")
    return "\n".join(lines)


def _write_report(P, R_full, R_post, T, F, path):
    c = P.loc["2026Q1":"2026Q3", ["cement_quarter_yoy", "cement_ytd_yoy"]].round(1)
    share = P.developer_share_of_re_credit.dropna()
    flagged = ", ".join(F[F.flag].quarter) or "none"
    sig = "\n".join(f"| {r.indicator} | {r.quarter} | {r.value:.2f} | {r.z_score:+.2f} | {r.flag} |"
                    for r in T.itertuples())
    text = f"""# Credit and construction signals for developer portfolios

Generated by `scripts/run_credit_signals.py` from public data only. Figures are in `outputs/`.

## Key findings

1. **Cement deliveries lead credit to property developers.** Since 2022, year-on-year growth in
   cement deliveries moves with developer-credit growth in the same quarter and up to two quarters
   ahead (Pearson {R_post.query("pair=='Cement deliveries vs credit to developers' and lead_quarters==2").pearson.iloc[0]:+.2f}
   at a two-quarter lead, n = {R_post.query("pair=='Cement deliveries vs credit to developers' and lead_quarters==2").n.iloc[0]}). Construction activity
   shows up in cement orders before it shows up in banks' developer books.
2. **Cement does not reliably lead transaction volumes.** No lead of 1-4 quarters is distinguishable from
   zero on both measures; the same-quarter Pearson value comes from the 2020-2021 lockdown and rebound.
3. **2026 so far.** Deliveries fell {c.loc['2026Q1','cement_quarter_yoy']:+.1f}% year on year in 2026Q1, the only quarter since
   2023 that the early-warning rule flags ({flagged}). Deliveries were still down 5.3% year-to-date at the end of
   May, then rebounded: 2026Q2 {c.loc['2026Q2','cement_quarter_yoy']:+.1f}%, 2026Q3 {c.loc['2026Q3','cement_quarter_yoy']:+.1f}%; year-to-date {c.loc['2026Q3','cement_ytd_yoy']:+.1f}% at the end of September.
   The Q1 drop coincided with heavy rainfall, which press reports cite as the main cause.
4. **Concentration is rising.** Loans to developers reached {share.iloc[-1]:.1f}% of real-estate credit in
   {share.index[-1]}, against {share.loc['2022Q1':].mean():.1f}% on average since 2022 (z = {T.set_index('indicator').loc["Developers' share of real-estate credit, %", 'z_score']:+.2f}, WATCH).
   More developer exposure while transaction volumes stay volatile is the main point for risk monitoring.

## Early-warning dashboard (latest quarter vs its 2022+ history)

WATCH = at least one standard deviation in the risky direction; ALERT = at least two.

| Indicator | Quarter | Value | z-score | Flag |
|---|---|---|---|---|
{sig}

## Lead/lag correlations, 2022Q1-2026Q2

{_fmt_corr(R_post)}

## Lead/lag correlations, full sample 2020Q1-2026Q2 (includes the lockdown)

{_fmt_corr(R_full)}

## How to read these results

- About 26 quarters is a short sample. These are indicative co-movements, not causal estimates or
  forecasts.
- Developer credit is a stock (outstanding loans), so it reacts to new lending and repayments with a lag.
- IPAI coverage widened to 83 land registries in 2025Q1; year-on-year comparisons across that break are less reliable.
- A few cement quarter-ends come from rounded press figures (flagged in `data/external`); they move
  quarterly growth by at most a few tenths of a point.
"""
    path.write_text(text)
