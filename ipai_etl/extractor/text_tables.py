"""Read the two text tables on page 1 of a bulletin: price change (%) and change in the
number of transactions (%) by category. These values are printed as text, so they are read
exactly (no chart measurement).

The bulletins are in French. The patterns below match the French category labels and the
parser returns English names:
    Global -> Global, Résidentiel -> Residential, Foncier -> Land,
    Professionnel or Commercial (older bulletins) -> Commercial
"""
import re

import pdfplumber

FR_TO_EN = {"Global": "Global", "Résidentiel": "Residential", "Foncier": "Land",
            "Professionnel": "Commercial", "Commercial": "Commercial"}
CATEGORIES_EN = ["Global", "Residential", "Land", "Commercial"]

_FR_LABELS = r"(Global|Résidentiel|Foncier|Commercial|Professionnel)"
ROW_RE = re.compile(_FR_LABELS + r"\s+(-?\d+(?:,\d+)?)\s+(-?\d+(?:,\d+)?)")
ORPHAN_NUMBERS_RE = re.compile(r"^\s*(-?\d+,\d+)\s+(-?\d+,\d+)\s*$")
ORPHAN_LABEL_RE = re.compile(r"^\s*" + _FR_LABELS + r"\s*$")


def _fix_split_rows(text):
    """Re-join a row whose label and two values were split across lines.

    A layout glitch in some bulletins (e.g. Q1-2026) puts the two numbers of a row on one line
    and its label on the next; the orphan number line is merged with the label that follows it.
    """
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        m_num = ORPHAN_NUMBERS_RE.match(lines[i])
        if m_num and i + 1 < len(lines) and ORPHAN_LABEL_RE.match(lines[i + 1]):
            label = ORPHAN_LABEL_RE.match(lines[i + 1]).group(1)
            out.append(f"{label} {m_num.group(1)} {m_num.group(2)}")
            i += 2
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def _to_float(s):
    return float(s.replace(",", "."))   # French decimal comma


_NUM_RE = re.compile(r"^[-−–]?\d+(?:[,.]\d+)?$")
_LABEL_RES = [
    ("Global", re.compile(r"^Global$")),
    ("Residential", re.compile(r"^R[eé]sidentiel$")),
    ("Land", re.compile(r"^Foncier$")),
    ("Commercial", re.compile(r"^(Commercial|Professionnel)$")),
]


def _num(s):
    return float(s.replace("−", "-").replace("–", "-").replace(",", "."))


def _parse_geometric(pdf_path):
    """Fallback: read page 1 by word coordinates when line-by-line text parsing fails.

    Each category label takes the two numbers to its right on the same line or, if the layout
    separated them, the two numbers of the nearest unlabelled line. Rows are split into two
    tables (prices, then transactions) at each 'Global' label.
    """
    with pdfplumber.open(pdf_path) as pdf:
        words = pdf.pages[0].extract_words(x_tolerance=2, y_tolerance=2)
    cy = lambda w: (w["top"] + w["bottom"]) / 2  # noqa: E731
    labels = []
    for w in words:
        for cat, rx in _LABEL_RES:
            if rx.match(w["text"].strip()):
                labels.append((cat, w))
    nums = [w for w in words if _NUM_RE.match(w["text"].strip())]
    used = set()
    rows = []
    for cat, lw in sorted(labels, key=lambda t: (t[1]["top"], t[1]["x0"])):
        same = sorted(
            [n for n in nums if abs(cy(n) - cy(lw)) <= 3.5 and n["x0"] > lw["x1"] - 1
             and id(n) not in used],
            key=lambda n: n["x0"],
        )
        if len(same) < 2:
            # unlabelled line: two numbers on a nearby line with no label
            near = [n for n in nums if id(n) not in used and abs(cy(n) - cy(lw)) <= 16]
            by_line = {}
            for n in near:
                by_line.setdefault(round(cy(n) / 3), []).append(n)
            cand = [sorted(v, key=lambda n: n["x0"]) for v in by_line.values() if len(v) >= 2]
            cand.sort(key=lambda v: abs(cy(v[0]) - cy(lw)))
            same = cand[0] if cand else same
        if len(same) >= 2:
            a, b = same[0], same[1]
            used.update({id(a), id(b)})
            rows.append((cat, _num(a["text"]), _num(b["text"]), lw["top"]))
        else:
            rows.append((cat, None, None, lw["top"]))
    tables = []
    for r in rows:
        if r[1] is None:
            continue  # a word in running text, not a table row
        if r[0] == "Global" or not tables:
            tables.append([])
        tables[-1].append(r)
    return tables[:2]


def parse_national_tables(pdf_path):
    """Return {'price_qoq', 'price_yoy', 'trans_pct_qoq', 'trans_pct_yoy', 'warnings'}.

    Each value is a dict keyed by English category (Global, Residential, Land, Commercial).
    The transaction percentages are used to cross-check the counts measured on the charts.
    """
    with pdfplumber.open(pdf_path) as pdf:
        txt = pdf.pages[0].extract_text() or ""
    txt = _fix_split_rows(txt)
    matches = [m for m in ROW_RE.findall(txt) if m[0] in FR_TO_EN]
    if len(matches) < 8:
        return _tables_from_geometry(pdf_path, len(matches))

    out = {"price_qoq": {}, "price_yoy": {}, "trans_pct_qoq": {}, "trans_pct_yoy": {}, "warnings": []}
    for label, qoq, yoy in matches[:4]:
        out["price_qoq"][FR_TO_EN[label]] = _to_float(qoq)
        out["price_yoy"][FR_TO_EN[label]] = _to_float(yoy)
    for label, qoq, yoy in matches[4:8]:
        out["trans_pct_qoq"][FR_TO_EN[label]] = _to_float(qoq)
        out["trans_pct_yoy"][FR_TO_EN[label]] = _to_float(yoy)
    return out


def _tables_from_geometry(pdf_path, n_text_rows):
    tables = _parse_geometric(pdf_path)
    out = {"price_qoq": {}, "price_yoy": {}, "trans_pct_qoq": {}, "trans_pct_yoy": {}, "warnings": []}
    keys = [("price_qoq", "price_yoy"), ("trans_pct_qoq", "trans_pct_yoy")]
    for ti, (kq, ky) in enumerate(keys):
        if ti >= len(tables):
            out["warnings"].append(f"{'price' if ti == 0 else 'transactions %'} table not found (geometric reading)")
            continue
        for cat, q, y, _ in tables[ti]:
            if q is not None and cat not in out[kq]:
                out[kq][cat] = q
                out[ky][cat] = y
        miss = [c for c in CATEGORIES_EN if c not in out[kq]]
        if miss:
            out["warnings"].append(f"{kq}: categories not read {miss} (text reading: {n_text_rows}/8 rows)")
    return out


if __name__ == "__main__":
    import glob
    for f in sorted(glob.glob("samples/*.pdf")):
        try:
            res = parse_national_tables(f)
            print(f, "OK", res["price_qoq"], res["trans_pct_qoq"])
        except Exception as e:
            print(f, "ERROR:", e)
