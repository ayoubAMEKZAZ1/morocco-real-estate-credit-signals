"""Assemble the time series (Q1-2015 to Q2-2026) from the values read in each bulletin."""
from charts import DOMINANT, ALL_CITIES

CATS = ["Global", "Residential", "Land", "Commercial"]
START, END = "Q1-2015", "Q2-2026"


def qidx(label):
    q, y = label.split("-")
    return int(y) * 4 + int(q[1]) - 1


def qlabel(i):
    return f"Q{i % 4 + 1}-{i // 4}"


def quarters_range(start=START, end=END):
    return [qlabel(i) for i in range(qidx(start), qidx(end) + 1)]


def _score(b):
    n = sum(len(b.get(k, {})) for k in ("price_qoq", "price_yoy", "cities10", "nat_window"))
    n += sum(len(w) for w in b.get("city_windows", {}).values())
    return n


def pick_primary(bulletins, diagnostics):
    """One bulletin per quarter. If a quarter has duplicates, keep the one with the most data
    (the others are still used to fill gaps)."""
    by_q = {}
    for b in bulletins:
        if not b.get("quarter"):
            continue
        by_q.setdefault(b["quarter"], []).append(b)
    primary = {}
    for q, lst in by_q.items():
        lst.sort(key=lambda b: (-_score(b), b["file"]))
        primary[q] = lst[0]
        for extra in lst[1:]:
            diagnostics.append({"file": extra["file"], "quarter": q, "field": "duplicate",
                                "message": f"same quarter as {lst[0]['file']} (kept); ignored "
                                           f"for the primary values"})
    return primary


def _lookup_window(t, primary, getter):
    """Value for quarter t: (1) read in its own bulletin (published value); otherwise (2) read in
    the earliest LATER bulletin whose chart window covers t (revised value, labelled as such)."""
    ti = qidx(t)
    b = primary.get(t)
    if b is not None:
        v = getter(b, 0)
        if v is not None:
            return v, "published"
    for q in sorted(primary, key=qidx):
        if qidx(q) <= ti:
            continue
        v = getter(primary[q], ti - qidx(q))
        if v is not None:
            return v, f"revised (read in {q})"
    return None, ""


def build_series(primary):
    quarters = quarters_range()
    S = {"quarters": quarters}

    def nat_get(b, off):
        w = b.get("nat_window", {})
        return w.get(off)

    nat = {}
    for t in quarters:
        v, src = _lookup_window(t, primary, nat_get)
        if v:
            nat[t] = ({"Residential": v[0], "Land": v[1], "Commercial": v[2],
                       "Global": sum(v)}, src)
    S["nat"] = nat

    S["city"] = {}
    for c in DOMINANT:
        def get(b, off, c=c):
            w = b.get("city_windows", {}).get(c)
            if not w:
                return None
            v = w.get(off)
            return v[0] if v else None
        d = {}
        for t in quarters:
            v, src = _lookup_window(t, primary, get)
            if v is not None:
                d[t] = (v, src)
        S["city"][c] = d

    S["tables"] = {t: primary[t] for t in quarters if t in primary}
    return S
