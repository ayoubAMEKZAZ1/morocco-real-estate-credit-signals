"""Render the IPAI dashboards with matplotlib, following the layout of the Tableau workbook:
1000 x 800 px dashboards, main area on the left (about 82%), legend column on the right (about 16%).
Tableau 10 palette; categories coloured in alphabetical order, as Tableau does."""
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
import numpy as np  # noqa: E402

from . import transform as T  # noqa: E402

BLUE, ORANGE, RED, TEAL = "#4e79a7", "#f28e2b", "#e15759", "#76b7b2"
CAT_COLOR = {"Land": BLUE, "Global": ORANGE, "Commercial": RED, "Residential": TEAL}
CATS = ["Global", "Residential", "Land", "Commercial"]
DIRECTION_COLOR = {"Positive": "#0a611b", "Neutral": "#76b7b2", "Negative": "#c11c2f",
                   "Methodological caution": "#edc948", "Structural negative": "#f4284e",
                   "Negative (deferred risk)": "#f598a7"}
GRID = "#e6e6e6"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#9a9a9a", "axes.linewidth": 0.7,
                     "svg.fonttype": "path", "font.size": 8})

W, H = 10.0, 8.0
MAIN_X0, MAIN_W, LEG_X0, LEG_W = 0.008, 0.824, 0.842, 0.15
NO_DATA = "Data not available"


def _fig():
    return plt.figure(figsize=(W, H), dpi=100, facecolor="white")


def _panel(fig, x, y, w, h, left=0.07, bottom=0.2, right=0.07, top=0.09):
    """Axes inside a panel (panel coordinates as figure fractions, origin top left)."""
    return fig.add_axes([x + w * left, 1 - (y + h) + h * bottom, w * (1 - left - right), h * (1 - bottom - top)])


def _title(fig, x, y, w, text, sub=None):
    fig.text(x + 0.004, 1 - y - 0.012, text, fontsize=9.2, fontweight="bold", color="#333333", va="top")
    if sub:
        fig.text(x + 0.004, 1 - y - 0.032, sub, fontsize=6.8, color="#666666", va="top")


def _style(ax):
    ax.grid(axis="y", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)


def _xticks(ax, labels, rot=90):
    n = len(labels)
    ax.set_xticks(range(n))
    ax.set_xticklabels(labels, rotation=rot, fontsize=6.4 if n > 26 else 7, ha="center")


def _zero_line(ax):
    ax.axhline(0, color="#7a7a7a", lw=0.8, zorder=1)


def _nodata(ax, msg):
    ax.text(0.5, 0.5, msg, ha="center", va="center", transform=ax.transAxes, fontsize=9, color="#888888")
    ax.set_xticks([])
    ax.set_yticks([])


# ---------------------------------------------------------------- panels
def draw_combo(ax, df, ylab_l="Price QoQ (%)", ylab_r="Transactions QoQ (%)"):
    """Bars (Price_QoQ, left axis) and a line with markers (Trans_QoQ, right axis); axes NOT synchronised,
    as in the Tableau workbook."""
    if df.empty or df[["Price_QoQ", "Trans_QoQ"]].isna().all().all():
        return _nodata(ax, NO_DATA)
    x = np.arange(len(df))
    _style(ax)
    ax.bar(x, df.Price_QoQ.values, color=BLUE, width=0.7, zorder=2)
    _zero_line(ax)
    ax.set_ylabel(ylab_l, fontsize=7.5, color=BLUE)
    ax.tick_params(axis="y", labelsize=7, colors=BLUE)
    _xticks(ax, df.Quarter.tolist())
    ax.set_xlim(-0.7, len(df) - 0.3)
    ax2 = ax.twinx()
    ax2.plot(x, df.Trans_QoQ.values, color=ORANGE, lw=1.6, marker="o", ms=3.2, zorder=3)
    ax2.set_ylabel(ylab_r, fontsize=7.5, color=ORANGE)
    ax2.tick_params(axis="y", labelsize=7, colors=ORANGE)
    ax2.spines["top"].set_visible(False)


def draw_yoy(ax, wide, ylab, annotate_break=False):
    if wide.empty:
        return _nodata(ax, NO_DATA)
    x = np.arange(len(wide))
    _style(ax)
    for c in sorted(CATS):
        ax.plot(x, wide[c].values, color=CAT_COLOR[c], lw=1.6, marker="o", ms=2.4, label=c)
    _zero_line(ax)
    ax.set_ylabel(ylab, fontsize=7.5)
    ax.tick_params(axis="y", labelsize=7)
    _xticks(ax, wide.index.tolist())
    ax.set_xlim(-0.5, len(wide) - 0.5)
    if annotate_break and "Q1-2025" in wide.index:
        i = list(wide.index).index("Q1-2025")
        ax.axvline(i - 0.5, color="#555555", ls=":", lw=1)
        ax.text(i - 0.4, ax.get_ylim()[1], "methodological break Q1-2025", fontsize=6, va="top", color="#555555")


def draw_margin(ax, m, ref):
    if m.empty:
        return _nodata(ax, NO_DATA)
    x = np.arange(len(m))
    _style(ax)
    ax.plot(x, m["Land − Residential"].values, color=TEAL, lw=1.7, marker="o", ms=2.6)
    ax.plot(x, m["Land − Commercial"].values, color=RED, lw=1.7, marker="o", ms=2.6)
    ax.axhline(ref, color="#555555", lw=1.0, ls="--")
    ax.set_ylabel("YoY price spread (points)", fontsize=7.5)
    ax.tick_params(axis="y", labelsize=7)
    _xticks(ax, m.Quarter.tolist())
    ax.set_xlim(-0.5, len(m) - 0.5)


def draw_season(ax, s):
    if s.empty:
        return _nodata(ax, "No complete year yet")
    x = s["Qtr"].values
    _style(ax)
    ax.fill_between(x, s.Price_QoQ.values, 0, color=BLUE, alpha=0.84, zorder=2)
    ax.plot(x, s.Price_QoQ.values, color=BLUE, lw=1.2)
    _zero_line(ax)
    ax.set_ylabel("Average price QoQ (%)", fontsize=7.5, color=BLUE)
    ax.tick_params(axis="y", labelsize=7, colors=BLUE)
    ax.set_xticks(x)
    ax.set_xticklabels([f"Q{int(t)}" for t in x], fontsize=8)
    ax.set_xlim(x.min() - 0.3, x.max() + 0.3)
    ax2 = ax.twinx()
    ax2.plot(x, s.Trans_QoQ.values, color=ORANGE, lw=1.8, marker="o", ms=3.5, zorder=3)
    ax2.set_ylabel("Average transactions QoQ (%)", fontsize=7.5, color=ORANGE)
    ax2.tick_params(axis="y", labelsize=7, colors=ORANGE)
    ax2.spines["top"].set_visible(False)


def draw_retro(ax, r, ylab):
    if r.empty:
        return _nodata(ax, NO_DATA)
    years = sorted(r.Year.unique())
    cats = sorted(CATS)
    bw, gap = 0.2, 0.35
    _style(ax)
    centers = []
    for yi, a in enumerate(years):
        base = yi * (4 * bw + gap)
        centers.append(base + 1.5 * bw)
        for ci, c in enumerate(cats):
            row = r[(r.Year == a) & (r.Category == c)]
            if row.empty:
                continue
            v = float(row.value.iloc[0])
            partial = not bool(row.complete.iloc[0])
            ax.bar(base + ci * bw, v, width=bw * 0.92, color=CAT_COLOR[c], zorder=2,
                   hatch="////" if partial else None, edgecolor="white" if partial else CAT_COLOR[c], lw=0.4)
    _zero_line(ax)
    ax.set_xticks(centers)
    labs = []
    for a in years:
        n = int(r[r.Year == a].n_quarters.max())
        labs.append(f"{a}" + ("" if n == 4 else f"\n({n} qtrs)"))
    ax.set_xticklabels(labs, fontsize=7.5)
    ax.set_ylabel(ylab, fontsize=7.5)
    ax.tick_params(axis="y", labelsize=7)
    if (~r.complete).any():
        ax.text(0.99, 0.02, "hatched = incomplete year", transform=ax.transAxes, ha="right", fontsize=6.3, color="#666")


def draw_forecast(ax, f, last_label, ylab="Change on previous quarter (%)"):
    if f is None or f.empty:
        return _nodata(ax, "Forecasts not available\n(series incomplete or too short)")
    f = f.sort_values("Chrono_order")
    x = np.arange(len(f))
    _style(ax)
    ax.plot(x, f.Optimistic.values, color=RED, lw=1.6, marker="o", ms=2.6)
    ax.plot(x, f.Central.values, color=BLUE, lw=2.0, marker="o", ms=3)
    ax.plot(x, f.Pessimistic.values, color=ORANGE, lw=1.6, marker="o", ms=2.6)
    ax.fill_between(x, f.Pessimistic.values, f.Optimistic.values, color=BLUE, alpha=0.07, zorder=1)
    _zero_line(ax)
    _xticks(ax, f.Quarter.tolist(), rot=0)
    ax.set_xlim(-0.3, len(f) - 0.7)
    ax.set_ylabel(ylab, fontsize=7.5)
    ax.tick_params(axis="y", labelsize=7)


def draw_signals(ax, sg, written_up_to, last_label):
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.0, 1.0, "Signal", fontsize=7.5, fontweight="bold", va="top", color="#555")
    ax.text(0.36, 1.0, "Direction", fontsize=7.5, fontweight="bold", va="top", color="#555")
    ax.text(0.555, 1.0, "Explanation", fontsize=7.5, fontweight="bold", va="top", color="#555")
    ax.plot([0, 1], [0.955, 0.955], color="#bbbbbb", lw=0.7)
    y = 0.93
    step = 0.88 / max(len(sg), 1)
    for _, r in sg.iterrows():
        col = DIRECTION_COLOR.get(r.Direction, "#333333")
        ax.text(0.0, y, "\n".join(textwrap.wrap(str(r.Signal), 27)[:3]), fontsize=6.2, va="top", color=col, fontweight="bold")
        ax.text(0.36, y, "\n".join(textwrap.wrap(str(r.Direction), 14, break_long_words=False)[:3]), fontsize=6.0, va="top", color=col, fontweight="bold")
        ax.text(0.555, y, "\n".join(textwrap.wrap(str(r.Explanation), 44)[:4]), fontsize=5.8, va="top", color="#333333")
        y -= step
    if last_label != written_up_to:
        ax.text(0.0, -0.02, f"Warning: signals written for data up to {written_up_to}; current data: "
                f"{last_label}. Review them.", fontsize=6.6, color="#c11c2f", va="top")


def draw_textbox(ax, text):
    ax.axis("off")
    ax.text(0.02, 0.92, "\n".join(textwrap.fill(p, 62) for p in text.split("\n")), fontsize=9.2, va="top",
            color="#333", linespacing=1.5)


# ---------------------------------------------------------------- legends
def _legend(fig, items, title, y, h=0.1):
    ax = fig.add_axes([LEG_X0, 1 - y - h, LEG_W, h])
    ax.axis("off")
    ax.text(0, 1, title, fontsize=7.2, fontweight="bold", va="top", color="#444")
    hs = [Patch(facecolor=c, label=l) if k == "p" else Line2D([0], [0], color=c, lw=2, marker="o", ms=3, label=l)
          for (l, c, k) in items]
    ax.legend(handles=hs, loc="upper left", bbox_to_anchor=(0, 0.88), frameon=False, fontsize=6.9,
              handlelength=1.4, labelspacing=0.5)


def _cat_legend(fig, y):
    _legend(fig, [(c, CAT_COLOR[c], "l") for c in sorted(CATS)], "Category", y, 0.14)


def _footer(fig, ctx):
    fig.text(0.008, 0.004, f"Source: IPAI, Bank Al-Maghrib / ANCFCC · data {ctx['first']} to {ctx['last']} · "
             f"generated {ctx['date']} · {ctx['note']}", fontsize=5.6, color="#888888", va="bottom")


MEASURES = [("Price QoQ", BLUE, "p"), ("Transactions QoQ", ORANGE, "l")]
FORECAST_LEGEND = [("Optimistic", RED, "l"), ("Central", BLUE, "l"), ("Pessimistic", ORANGE, "l")]
RETRO_SUB = "compound growth of the 4 quarterly changes"


# ---------------------------------------------------------------- dashboards
def build_dashboards(D):
    """D = dict: hist, last, first, fprev (forecast table), signals, cfg, date, validation (n_ok, n_tot).
    Return ({file_name: Figure}, {category: Figure} variants of the credit product profile)."""
    cfg, hist, last = D["cfg"], D["hist"], D["last"]
    gc, gc_note = T.global_combo(hist, cfg)
    mg = T.margin(hist, cfg)
    ss, ss_note, _ = T.seasonality(hist, last, cfg)
    rp, rt = T.retro(hist, "Price_QoQ"), T.retro(hist, "Trans_QoQ")
    yp, yt = T.yoy_wide(hist, "Price_YoY"), T.yoy_wide(hist, "Trans_YoY")
    brk = cfg["annotate_q1_2025_break"]
    fp = D["fprev"]
    fglob = fp[(fp.Category == "Global") & (fp.Metric == "price")] if fp is not None and len(fp) else None
    ctx = {"first": D["first"], "last": last, "date": D["date"], "note": ""}
    figs = {}

    def combo_title(note):
        return "Price QoQ (bars) and transactions QoQ (line), " + note

    # 1. Overview
    f = _fig()
    ctx["note"] = gc_note
    _title(f, MAIN_X0, 0.01, MAIN_W, "Overview", combo_title(gc_note))
    draw_combo(_panel(f, MAIN_X0, 0.06, MAIN_W, 0.92, bottom=0.12), gc)
    _legend(f, MEASURES, "Measures", 0.83, 0.1)
    f.text(LEG_X0, 0.95, f"Quarters:\n{D['first']} to {last}", fontsize=7, color="#444", va="top")
    _footer(f, ctx)
    figs["1_overview"] = f

    # 2. Overview & key signals
    f = _fig()
    _title(f, MAIN_X0, 0.01, MAIN_W, "Overview & key signals", combo_title(gc_note))
    draw_combo(_panel(f, MAIN_X0, 0.045, MAIN_W, 0.45, bottom=0.2), gc)
    _title(f, MAIN_X0, 0.50, MAIN_W / 2, "Prices, year on year, by category")
    draw_yoy(_panel(f, MAIN_X0, 0.52, MAIN_W / 2, 0.47, left=0.13, right=0.03, bottom=0.2), yp, "Price YoY (%)", brk)
    _title(f, MAIN_X0 + MAIN_W / 2, 0.50, MAIN_W / 2, "Transactions, year on year, by category")
    draw_yoy(_panel(f, MAIN_X0 + MAIN_W / 2, 0.52, MAIN_W / 2, 0.47, left=0.13, right=0.03, bottom=0.2), yt,
             "Transactions YoY (%)", brk)
    _legend(f, MEASURES, "Measures", 0.77, 0.1)
    _cat_legend(f, 0.86)
    _footer(f, ctx)
    figs["2_overview_key_signals"] = f

    # 3. Market risk
    f = _fig()
    _title(f, MAIN_X0, 0.01, MAIN_W, "Market risk: prices, year on year")
    draw_yoy(_panel(f, MAIN_X0, 0.045, MAIN_W, 0.45, bottom=0.2), yp, "Price YoY (%)", brk)
    _title(f, MAIN_X0, 0.50, MAIN_W, "Market risk: transactions, year on year")
    draw_yoy(_panel(f, MAIN_X0, 0.535, MAIN_W, 0.45, bottom=0.2), yt, "Transactions YoY (%)", brk)
    _cat_legend(f, 0.01)
    _footer(f, ctx)
    figs["3_market_risk"] = f

    # 4. Credit product profile (one variant per category = collateral type)
    variants = {}
    for cat in CATS:
        f = _fig()
        _title(f, MAIN_X0, 0.01, MAIN_W, f"Credit product profile: {cat}", combo_title(f"{cat} category"))
        draw_combo(_panel(f, MAIN_X0, 0.06, MAIN_W, 0.92, bottom=0.12), T.profile(hist, cat))
        _legend(f, MEASURES, "Measures", 0.9, 0.09)
        f.text(LEG_X0, 0.97, f"Category: {cat}", fontsize=7.5, fontweight="bold", color="#444", va="top")
        _footer(f, ctx)
        variants[cat] = f
    figs["4_credit_product_profile"] = variants[cfg["default_profile_category"]]

    # 5. Margin & seasonality
    f = _fig()
    _title(f, MAIN_X0, 0.01, MAIN_W, "Developer margin: YoY price spread of land vs residential / commercial",
           "dashed: reference line = %s" % cfg["margin_reference"])
    draw_margin(_panel(f, MAIN_X0, 0.06, MAIN_W, 0.43, bottom=0.2), mg, cfg["margin_reference"])
    _title(f, MAIN_X0, 0.50, MAIN_W, "Seasonality: average profile by quarter", ss_note)
    draw_season(_panel(f, MAIN_X0, 0.545, MAIN_W, 0.44, bottom=0.14), ss)
    _legend(f, [("Land − Commercial", RED, "l"), ("Land − Residential", TEAL, "l")], "Spreads", 0.01, 0.13)
    _legend(f, MEASURES, "Seasonality", 0.16, 0.1)
    _footer(f, ctx)
    figs["5_margin_and_seasonality"] = f

    hw = MAIN_W / 2

    def retro_row(f):
        _title(f, MAIN_X0, 0.01, hw, "Retrospective: annual price growth (%)", RETRO_SUB)
        draw_retro(_panel(f, MAIN_X0, 0.055, hw, 0.43, left=0.12, right=0.03, bottom=0.14), rp, "Prices (%)")
        _title(f, MAIN_X0 + hw, 0.01, hw, "Retrospective: annual transactions growth (%)", RETRO_SUB)
        draw_retro(_panel(f, MAIN_X0 + hw, 0.055, hw, 0.43, left=0.12, right=0.03, bottom=0.14), rt, "Transactions (%)")

    def forecast_panel(f):
        _title(f, MAIN_X0 + hw, 0.50, hw, "Forecasts: Global, prices", "central · pessimistic · optimistic")
        draw_forecast(_panel(f, MAIN_X0 + hw, 0.545, hw, 0.43, left=0.12, right=0.03, bottom=0.12), fglob, last)

    # 6. Retrospective, signals & forecast
    f = _fig()
    retro_row(f)
    _title(f, MAIN_X0, 0.50, hw, "Signals")
    draw_signals(f.add_axes([MAIN_X0 + 0.005, 0.07, hw - 0.012, 0.40]), D["signals"], D["signals_up_to"], last)
    forecast_panel(f)
    _cat_legend(f, 0.01)
    _legend(f, [(k, v, "p") for k, v in DIRECTION_COLOR.items()], "Direction", 0.17, 0.2)
    _legend(f, FORECAST_LEGEND, "Forecast", 0.40, 0.1)
    _footer(f, ctx)
    figs["6_retro_signals_forecast"] = f

    # 7. Model & forecast
    f = _fig()
    retro_row(f)
    n_ok, n_tot = D["validation"]
    txt = (f"Validated by walk-forward backtesting\nagainst 2 naive benchmark models:\n"
           f"the selected model beats both on {n_ok} of the {n_tot} series tested.")
    if n_tot and n_ok < n_tot:
        txt += f"\nCaution: {n_tot - n_ok} series do not beat them; read those forecasts carefully."
    draw_textbox(f.add_axes([MAIN_X0 + 0.005, 0.07, hw - 0.012, 0.40]), txt)
    forecast_panel(f)
    _cat_legend(f, 0.01)
    _legend(f, FORECAST_LEGEND, "Forecast", 0.17, 0.1)
    _footer(f, ctx)
    figs["7_model_and_forecast"] = f
    return figs, variants


def build_forecast_grid(D):
    """Annex: forecasts for the 8 series (4 categories x prices/transactions)."""
    fp, last = D["fprev"], D["last"]
    f = plt.figure(figsize=(10, 8), dpi=100, facecolor="white")
    f.text(0.01, 0.985, "Annex: forecasts for the 8 series (central, pessimistic, optimistic)", fontsize=10,
           fontweight="bold", va="top")
    for i, cat in enumerate(CATS):
        for j, met in enumerate(("price", "transactions")):
            ax = f.add_axes([0.07 + j * 0.49, 0.78 - i * 0.23, 0.41, 0.15])
            sub = fp[(fp.Category == cat) & (fp.Metric == met)] if fp is not None and len(fp) else None
            draw_forecast(ax, sub, last, ylab="%")
            ax.set_title(f"{cat}: {met}", fontsize=8, loc="left")
    f.text(0.01, 0.004, "Statistical trend forecasts, not a credit decision recommendation.", fontsize=6, color="#888")
    return f
