"""Self-contained HTML page (embedded SVGs, no external dependency) holding all dashboards."""
import html
import io

import matplotlib.pyplot as plt

TITLES = {
    "1_overview": "Overview",
    "2_overview_key_signals": "Overview & key signals",
    "3_market_risk": "Market risk",
    "4_credit_product_profile": "Credit product profile",
    "5_margin_and_seasonality": "Margin & seasonality",
    "6_retro_signals_forecast": "Retrospective, signals & forecast",
    "7_model_and_forecast": "Model & forecast",
    "8_forecast_annex": "Annex: forecasts (8 series)",
}


def _svg(fig):
    b = io.StringIO()
    fig.savefig(b, format="svg", facecolor="white")
    s = b.getvalue()
    return s[s.index("<svg"):]


def build_html(figs, variants, annex, notes, meta, path):
    tabs, panels = [], []
    for i, (k, fig) in enumerate(figs.items()):
        tabs.append(f'<button class="tab{" on" if i == 0 else ""}" data-t="p{i}">{html.escape(TITLES[k])}</button>')
        if k == "4_credit_product_profile":
            opts = "".join(f'<option value="{c}"{" selected" if variants[c] is fig else ""}>{c}</option>' for c in variants)
            body = f'<label>Category: <select id="cat">{opts}</select></label>' + "".join(
                f'<div class="v" data-c="{c}"{"" if variants[c] is fig else " hidden"}>{_svg(v)}</div>' for c, v in variants.items())
        else:
            body = _svg(fig)
        panels.append(f'<section class="pn{" on" if i == 0 else ""}" id="p{i}">{body}</section>')
    n = len(figs)
    tabs.append(f'<button class="tab" data-t="p{n}">{TITLES["8_forecast_annex"]}</button>')
    panels.append(f'<section class="pn" id="p{n}">{_svg(annex)}</section>')
    tabs.append(f'<button class="tab" data-t="p{n + 1}">Notes & checks</button>')
    li = "".join(f"<li>{html.escape(m)}</li>" for m in notes) or "<li>No anomaly.</li>"
    panels.append(f'<section class="pn" id="p{n + 1}"><h2>Notes and checks for this run</h2><ul>{li}</ul></section>')
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IPAI dashboards</title><style>
body{{font-family:system-ui,Arial,sans-serif;margin:0;background:#f4f5f7;color:#222}}
header{{background:#1F3864;color:#fff;padding:14px 22px}} header h1{{margin:0;font-size:18px}} header p{{margin:4px 0 0;font-size:12px;opacity:.85}}
nav{{display:flex;flex-wrap:wrap;gap:6px;padding:10px 22px;background:#fff;border-bottom:1px solid #ddd}}
.tab{{border:1px solid #c8d0de;background:#fff;padding:6px 12px;border-radius:6px;cursor:pointer;font-size:13px}}
.tab.on{{background:#1F3864;color:#fff;border-color:#1F3864}}
.pn{{display:none;padding:16px 22px}} .pn.on{{display:block}} .pn svg{{max-width:100%;height:auto;background:#fff;box-shadow:0 1px 4px #0002}}
label{{display:block;margin-bottom:8px;font-size:13px}} li{{margin:6px 0;font-size:13px}} [hidden]{{display:none!important}}
</style></head><body><header><h1>IPAI quarterly dashboards</h1>
<p>{html.escape(meta)}</p></header><nav>{''.join(tabs)}</nav>{''.join(panels)}
<script>
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{{document.querySelectorAll('.tab,.pn').forEach(e=>e.classList.remove('on'));
b.classList.add('on');document.getElementById(b.dataset.t).classList.add('on')}});
var s=document.getElementById('cat'); if(s) s.onchange=()=>document.querySelectorAll('.v').forEach(v=>v.hidden=v.dataset.c!==s.value);
</script></body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
