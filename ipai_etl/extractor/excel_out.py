"""Write the single Excel workbook (20 sheets plus a Diagnostics sheet)."""
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from assemble import CATS
from charts import ALL_CITIES, DOMINANT

HDR_FILL = PatternFill("solid", fgColor="1F3864")
HDR_FONT = Font(bold=True, color="FFFFFF")
REV_FILL = PatternFill("solid", fgColor="FCE4D6")   # revised value (read in a later bulletin)
NA_FILL = PatternFill("solid", fgColor="EDEDED")    # value not available


def _slug(s):
    return s.replace("é", "e").replace("è", "e").replace(" ", "_")


def _write(ws, headers, rows, fmts, source_cols=()):
    """rows: list of lists; None = empty greyed cell.
    source_cols: indexes of text 'source' columns; a value starting with 'revised' also
    highlights the value cell to its left."""
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font = HDR_FILL, HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for r in rows:
        ws.append(r)
    for ri in range(2, len(rows) + 2):
        for ci, f in enumerate(fmts, start=1):
            cell = ws.cell(row=ri, column=ci)
            if f:
                cell.number_format = f
            if ci > 1 and cell.value is None and ci not in source_cols:
                cell.fill = NA_FILL
        for sc in source_cols:
            src = ws.cell(row=ri, column=sc).value
            if src and str(src).startswith("revised"):
                ws.cell(row=ri, column=sc - 1).fill = REV_FILL
                ws.cell(row=ri, column=sc).fill = REV_FILL
    ws.freeze_panes = "B2"
    ws.column_dimensions["A"].width = 12
    for ci in range(2, len(headers) + 1):
        ws.column_dimensions[get_column_letter(ci)].width = 24
    ws.row_dimensions[1].height = 45


def write_workbook(S, diagnostics, path):
    Q = S["quarters"]
    T = S["tables"]
    wb = Workbook()
    wb.remove(wb.active)

    def tab(t, *keys):
        d = T.get(t)
        for k in keys:
            if not isinstance(d, dict) or k not in d:
                return None
            d = d[k]
        return d

    def nat(t, cat):
        e = S["nat"].get(t)
        return (e[0][cat], e[1]) if e else (None, "")

    # 01 - national prices
    ws = wb.create_sheet("01_Price_Global")
    _write(ws, ["Quarter", "Price change QoQ (%)", "Price change YoY (%)"],
           [[t, tab(t, "price_qoq", "Global"), tab(t, "price_yoy", "Global")] for t in Q],
           [None, "0.0", "0.0"])

    # 02 - national transaction counts
    ws = wb.create_sheet("02_Transactions_Global")
    rows = []
    for t in Q:
        v, s = nat(t, "Global")
        rows.append([t, v, s])
    _write(ws, ["Quarter", "Number of transactions (Global)", "Value source"],
           rows, [None, "#,##0", None], source_cols=(3,))

    # 03-06 - asset categories (the collateral types behind each credit product)
    for i, cat in enumerate(CATS):
        ws = wb.create_sheet(f"{3 + i:02d}_Cat_{_slug(cat)}")
        rows = []
        for t in Q:
            v, s = nat(t, cat)
            rows.append([t, tab(t, "price_qoq", cat), tab(t, "price_yoy", cat),
                         tab(t, "trans_pct_qoq", cat), tab(t, "trans_pct_yoy", cat), v, s])
        _write(ws, ["Quarter", "Price change QoQ (%)", "Price change YoY (%)",
                    "Transactions change QoQ (%)", "Transactions change YoY (%)",
                    f"Number of transactions ({cat})", "Transactions value source"],
               rows, [None, "0.0", "0.0", "0.0", "0.0", "#,##0", None], source_cols=(7,))

    # 07-10 - dominant cities
    for i, city in enumerate(DOMINANT):
        ws = wb.create_sheet(f"{7 + i:02d}_{_slug(city)}")
        rows = []
        for t in Q:
            e = S["city"][city].get(t)
            rows.append([t, e[0] if e else None, e[1] if e else "",
                         tab(t, "cities10", city, "price_qoq")])
        _write(ws, ["Quarter", f"Number of transactions ({city})", "Transactions value source",
                    "Price change QoQ (%)"],
               rows, [None, "#,##0", None, "0.0"], source_cols=(3,))

    # 11-20 - ten main cities
    for i, city in enumerate(ALL_CITIES):
        ws = wb.create_sheet(f"{11 + i:02d}_C10_{_slug(city)}")
        rows = [[t, tab(t, "cities10", city, "price_qoq"), tab(t, "cities10", city, "trans_qoq")]
                for t in Q]
        _write(ws, ["Quarter", "Price change QoQ (%)", "Transactions change QoQ (%)"],
               rows, [None, "0.0", "0.0"])

    # Diagnostics
    ws = wb.create_sheet("Diagnostics")
    ws.append(["file", "quarter", "field", "message"])
    for c in range(1, 5):
        ws.cell(row=1, column=c).fill, ws.cell(row=1, column=c).font = HDR_FILL, HDR_FONT
    for d in diagnostics:
        ws.append([d.get("file"), d.get("quarter"), d.get("field"), d.get("message")])
    for col, w in zip("ABCD", (34, 12, 30, 110)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    wb.save(path)
