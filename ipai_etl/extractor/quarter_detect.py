"""Detect the quarter and year of each IPAI bulletin.

The bulletins are published in French, so the regular expressions match French phrases
(e.g. "au cours du 4ème trimestre 2016" = "during the 4th quarter of 2016").
"""
import re
import pdfplumber

QUARTER_RE = re.compile(
    r"au\s+cours\s+du\s+(\d)\s*(?:er|ère|ème|eme|EME|ER)?\s*trimestre\s+(\d{4})",
    re.IGNORECASE,
)

# Fallback: pattern like "T4-2016" or "T4 2016" appearing in the title block
QUARTER_RE_FALLBACK = re.compile(r"\bT([1-4])[\s\-_]?(\d{4})\b")


def detect_quarter(pdf_path, max_pages=2):
    """Return (quarter:int, year:int, label:str e.g. 'Q4-2016') or None."""
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for p in pdf.pages[:max_pages]:
            t = p.extract_text(layout=True) or ""
            text += "\n" + t
        m = QUARTER_RE.search(text)
        if m:
            q, y = int(m.group(1)), int(m.group(2))
            return q, y, f"Q{q}-{y}"
        m = QUARTER_RE_FALLBACK.search(text)
        if m:
            q, y = int(m.group(1)), int(m.group(2))
            return q, y, f"Q{q}-{y}"
    return None


if __name__ == "__main__":
    import sys, glob
    for f in sorted(glob.glob("samples/*.pdf")):
        res = detect_quarter(f)
        print(f, "->", res)
