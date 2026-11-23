"""Process one bulletin PDF: return every raw value read (text tables and chart windows)
plus the list of warnings."""
import os

import pdfplumber

from quarter_detect import detect_quarter
from text_tables import parse_national_tables
from city_table import parse_city_table
import charts

CATS = ["Residential", "Land", "Commercial"]


def _tol(v0, v1):
    """Tolerance (percentage points) for the internal check: 2 points plus the effect of chart
    granularity (bar heights in the PDFs are quantised to roughly 100 transactions)."""
    m = max(min(v0, v1), 1)
    return 2 + 15000.0 / m


def process_bulletin(pdf_path):
    fname = os.path.basename(pdf_path)
    diags = []

    def d(field, msg):
        diags.append({"file": fname, "quarter": label, "field": field, "message": msg})

    label = None
    qinfo = detect_quarter(pdf_path)
    if not qinfo:
        d("quarter_detection", "quarter not detected; bulletin skipped")
        return {"file": fname, "quarter": None, "diags": diags}
    label = qinfo[2]
    out = {"file": fname, "quarter": label, "diags": diags,
           "price_qoq": {}, "price_yoy": {}, "trans_pct_qoq": {}, "trans_pct_yoy": {},
           "cities10": {}, "nat_window": {}, "city_windows": {}}

    try:
        t = parse_national_tables(pdf_path)
        for k in ("price_qoq", "price_yoy", "trans_pct_qoq", "trans_pct_yoy"):
            out[k] = t[k]
        for w in t.get("warnings", []):
            d("national_table", w)
    except Exception as e:
        d("national_table", f"error: {e}")

    try:
        out["cities10"] = parse_city_table(pdf_path)
    except Exception as e:
        d("ten_city_table", f"error: {e}")

    try:
        with pdfplumber.open(pdf_path) as pdf:
            caches = [charts.PageCache(p) for p in pdf.pages]
            win, warn, info = charts.national_window(pdf, caches)
            out["nat_window"] = win
            if warn:
                d("national_transactions", warn)
            try:
                cw = charts.city_windows(pdf, caches)
            except Exception as e:
                cw = {}
                d("dominant_cities", f"error: {e}")
            for city in charts.DOMINANT:
                r = cw.get(city)
                if r is None:
                    d(f"city_{city}", "chart not present in this bulletin")
                    continue
                out["city_windows"][city] = r["window"]
                if r["warning"]:
                    d(f"city_{city}", r["warning"])
    except Exception as e:
        d("charts", f"error: {e}")

    # internal check: change implied by the last two bars vs the published %
    nat = out["nat_window"]
    if 0 in nat and -1 in nat:
        for i, cat in enumerate(CATS):
            pub = out["trans_pct_qoq"].get(cat)
            if pub is not None and nat[-1][i]:
                imp = (nat[0][i] / nat[-1][i] - 1) * 100
                if abs(imp - pub) > _tol(nat[0][i], nat[-1][i]):
                    d(f"internal_check_{cat}", f"chart: {imp:.1f}% vs published table: {pub:.1f}% (abnormal gap)")
        tot0, tot1 = sum(nat[0]), sum(nat[-1])
        pub = out["trans_pct_qoq"].get("Global")
        if pub is not None and tot1:
            imp = (tot0 / tot1 - 1) * 100
            if abs(imp - pub) > _tol(tot0, tot1):
                d("internal_check_Global", f"chart: {imp:.1f}% vs published table: {pub:.1f}% (abnormal gap)")
    for city, w in out["city_windows"].items():
        pub = out["cities10"].get(city, {}).get("trans_qoq")
        if pub is not None and 0 in w and -1 in w and w[-1][0]:
            imp = (w[0][0] / w[-1][0] - 1) * 100
            if abs(imp - pub) > _tol(w[0][0], w[-1][0]):
                d(f"internal_check_{city}", f"chart: {imp:.1f}% vs ten-city table: {pub:.1f}% (abnormal gap)")
    return out
