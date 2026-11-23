"""Read the 'ten main cities' table: % change in price and in the number of transactions,
per city, from each city's 'Global' row. The values are text, so they are read exactly; the
page is split into left and right halves because the PDF places two sub-tables side by side.

The bulletins are in French: 'Terrain urbain' = urban land, 'quelques grandes villes' = some
major cities (the table title)."""
import re
import pdfplumber

from names import city_en

CITY_BLOCK_RE = re.compile(
    r"^([A-ZÉÈÀÎ][\wÀ-ÿ'’ \-]*?)\s+Terrain urbain.*?Global\s+(-?[\d,]+|-)\s+(-?[\d,]+|-)",
    re.MULTILINE | re.DOTALL,
)
CITY_NAME_RE = re.compile(r"^([A-ZÉÈÀÎ][\wÀ-ÿ'’ \-]*?)\s+Terrain urbain", re.MULTILINE)


def _to_float(s):
    if s is None or s.strip() == "-":
        return None
    return float(s.replace(",", "."))


def _find_city_table_page(pdf):
    for page in pdf.pages:
        txt = page.extract_text() or ""
        if "quelques grandes villes" in txt.lower() and txt.count("Terrain urbain") >= 2:
            return page
    return None


def _parse_half(text):
    """Split one half-page into per-city blocks (from a city name to the next one or the end of
    the table) and read the Global row of each block."""
    names = [m.start() for m in CITY_NAME_RE.finditer(text)]
    labels = CITY_NAME_RE.findall(text)
    results = {}
    for i, (start, label) in enumerate(zip(names, labels)):
        end = names[i + 1] if i + 1 < len(names) else len(text)
        block = text[start:end]
        m = re.search(r"Global\s+(-?[\d,]+|-)\s+(-?[\d,]+|-)", block)
        if m:
            results[city_en(label)] = (_to_float(m.group(1)), _to_float(m.group(2)))
    return results


def parse_city_table(pdf_path):
    """Return {city: {'price_qoq': float|None, 'trans_qoq': float|None}}."""
    with pdfplumber.open(pdf_path) as pdf:
        page = _find_city_table_page(pdf)
        if page is None:
            raise ValueError(f"{pdf_path}: ten-city table not found")
        w = page.width
        full = page.extract_text() or ""
        k = full.lower().index("quelques grandes villes")
        j = full.find("Appartement", k)
        header = full[k:j if j > k else k + 400].lower()
        # Some older bulletins (e.g. Q3-2015) have NO transactions column: their two columns
        # are the price change on the previous quarter and on the same quarter a year earlier.
        has_trans = "transactions" in header
        left = page.crop((0, 0, w * 0.52, page.height)).extract_text() or ""
        right = page.crop((w * 0.48, 0, w, page.height)).extract_text() or ""

    out = {}
    for half in (left, right):
        out.update(_parse_half(half))

    out_clean = {
        city: {"price_qoq": v[0],
               "trans_qoq": v[1] if has_trans else None,
               "table_without_transactions": not has_trans}
        for city, v in out.items()
    }
    return out_clean


if __name__ == "__main__":
    import glob
    for f in sorted(glob.glob("samples/*.pdf")):
        try:
            res = parse_city_table(f)
            print(f, "->", len(res), "cities:", res)
        except Exception as e:
            print(f, "ERROR:", e)
