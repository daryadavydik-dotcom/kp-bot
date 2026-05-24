from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment

_PROJECT_ROOT = Path(__file__).parent.parent
_SIGNATURE_PATH = _PROJECT_ROOT / "Подпись.png"
_STAMP_PATH = _PROJECT_ROOT / "Печать.png"


def _format_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _fmt_num(value) -> str:
    """Format number: integer if whole, else 2 decimal places."""
    try:
        f = float(value)
        return str(int(f)) if f == int(f) else f"{f:.2f}"
    except (TypeError, ValueError):
        return str(value) if value else ""


def build_replacements(kp_data: dict, kp_number: str) -> dict:
    today = date.today()
    valid_until = today + timedelta(days=14)
    client = kp_data.get("client", {})
    items = kp_data.get("items", [])

    replacements = {
        "kp_number": kp_number,
        "date": _format_date(today),
        "kp_valid_until": _format_date(valid_until),
        "client_name": client.get("client_name", ""),
        "contact_person": client.get("contact_person", ""),
        "phone": client.get("phone", ""),
        "manager": client.get("manager", ""),
        "delivery_time": client.get("delivery_time", ""),
        "payment_terms": client.get("payment_terms", ""),
        "company_contacts": client.get("company_contacts", ""),
    }

    total_sum = 0.0
    for i in range(20):
        n = i + 1
        item = items[i] if i < len(items) else {}
        product = item.get("product", "")
        unit = item.get("unit", "")
        qty = item.get("qty")
        price = item.get("price")

        if product:
            row_num = str(i + 1)
            qty_str = _fmt_num(qty) if qty is not None else ""
            price_str = _fmt_num(price) if price is not None else ""
            try:
                line_total = float(qty or 0) * float(price or 0)
                total_str = _fmt_num(line_total)
                total_sum += line_total
            except (TypeError, ValueError):
                total_str = ""
        else:
            row_num = ""
            qty_str = ""
            price_str = ""
            total_str = ""

        replacements[f"row_num_{n}"] = row_num
        replacements[f"product_{n}"] = product
        replacements[f"unit_{n}"] = unit
        replacements[f"qty_{n}"] = qty_str
        replacements[f"price_{n}"] = price_str
        replacements[f"total_{n}"] = total_str

    replacements["total_sum"] = _fmt_num(total_sum) if total_sum else ""
    return replacements


def fill_template(template_bytes: bytes, replacements: dict) -> bytes:
    """Replace all {{key}} placeholders in every cell of every sheet."""
    import re as _re
    wb = openpyxl.load_workbook(BytesIO(template_bytes))

    empty_product_nums = {
        n for n in range(1, 21)
        if not replacements.get(f"product_{n}", "")
    }

    for ws in wb.worksheets:
        # --- Pass 1: locate placeholder positions ---
        _CLIENT_KEYS = {
            "client_name", "contact_person", "phone", "manager",
            "delivery_time", "payment_terms", "company_contacts",
        }
        product_placeholder_rows: dict[int, int] = {}  # product_num → row
        product_name_col: int | None = None
        client_field_rows: set[int] = set()

        for row in ws.iter_rows():
            for cell in row:
                if not isinstance(cell.value, str):
                    continue
                m_prod = _re.fullmatch(r'\{\{product_(\d+)\}\}', cell.value)
                if m_prod:
                    n = int(m_prod.group(1))
                    product_placeholder_rows[n] = cell.row
                    product_name_col = cell.column
                    continue
                m_any = _re.fullmatch(r'\{\{([^}]+)\}\}', cell.value)
                if m_any and m_any.group(1) in _CLIENT_KEYS:
                    client_field_rows.add(cell.row)

        # --- Pass 2: replace placeholders ---
        for row in ws.iter_rows():
            for cell in row:
                if not isinstance(cell.value, str):
                    continue
                v = cell.value
                sole = _re.fullmatch(r'\{\{([^}]+)\}\}', v)
                if sole:
                    key = sole.group(1)
                    value = replacements.get(key, "")
                    if value == "" or value is None:
                        cell.value = None
                    else:
                        try:
                            fv = float(str(value))
                            cell.value = int(fv) if fv == int(fv) else fv
                        except (ValueError, TypeError):
                            cell.value = str(value)
                    continue
                new_value = v
                for key, value in replacements.items():
                    ph = "{{" + key + "}}"
                    if ph in new_value:
                        new_value = new_value.replace(ph, str(value) if value else "")
                new_value = _re.sub(r"\{\{[^}]+\}\}", "", new_value)
                if new_value != v:
                    cell.value = new_value if new_value.strip() else None

        # --- Pass 3: formatting ---

        # Widen and wrap the Наименование column
        if product_name_col:
            col_letter = openpyxl.utils.get_column_letter(product_name_col)
            ws.column_dimensions[col_letter].width = 48

        # Wrap text + row height for filled product rows
        for n in range(1, 21):
            row_num = product_placeholder_rows.get(n)
            if not row_num or n in empty_product_nums:
                continue
            if product_name_col:
                name_cell = ws.cell(row=row_num, column=product_name_col)
                name_cell.alignment = Alignment(wrap_text=True, vertical="top")
                text_len = len(str(name_cell.value or ""))
                lines = max(1, -(-text_len // 45))
                ws.row_dimensions[row_num].height = max(30, lines * 18)

        # Widen column A so labels like "Контактное лицо:" fit on one line
        ws.column_dimensions["A"].width = 22

        # Center header rows; left-align client data rows
        first_product_row = min(product_placeholder_rows.values()) if product_placeholder_rows else 999
        header_end = max(1, first_product_row - 2)
        for row in ws.iter_rows(min_row=1, max_row=header_end):
            for cell in row:
                if cell.value is None:
                    continue
                if cell.row in client_field_rows:
                    # Column A has labels — no wrap, left-aligned
                    # Other columns have values — wrap allowed
                    no_wrap = (cell.column == 1)
                    cell.alignment = Alignment(
                        horizontal="left",
                        vertical="center",
                        wrap_text=not no_wrap,
                    )
                else:
                    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # Explicitly left-align row 8 (template row with manager field)
        for cell in ws[8]:
            if cell.value is not None:
                cell.alignment = Alignment(horizontal="left", vertical="center")

        # --- Pass 4: delete empty product rows (bottom → top) ---
        rows_to_delete = sorted(
            [product_placeholder_rows[n] for n in empty_product_nums if n in product_placeholder_rows],
            reverse=True,
        )
        for row_num in rows_to_delete:
            ws.delete_rows(row_num)

        # --- Pass 5: insert signature and stamp images ---
        # Find "М.П." cell — stamp goes there, signature one row above in same column
        mp_cell = None
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and "м.п" in cell.value.lower():
                    mp_cell = cell
                    break
            if mp_cell:
                break

        # Find anchor rows by text
        dir_row = None   # row with "Генеральный директор"
        mp_row = None    # row with "М.П."
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    if dir_row is None and "директор" in cell.value.lower():
                        dir_row = cell.row
                    if mp_row is None and "м.п" in cell.value.lower():
                        mp_row = cell.row

        # Helper: add image centered horizontally in column B
        # Column B width = 48 chars ≈ 336px; center offset = (336 - img_width) / 2
        from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
        from openpyxl.drawing.xdr import XDRPositiveSize2D
        _EMU = 9525  # 1 pixel in EMU

        def _add_centered(img, row_0based, img_w, img_h):
            col_b_width_px = 336  # column B width in pixels (48 char units)
            offset_px = max(0, (col_b_width_px - img_w) // 2)
            marker = AnchorMarker(col=1, colOff=offset_px * _EMU, row=row_0based, rowOff=0)
            size = XDRPositiveSize2D(img_w * _EMU, img_h * _EMU)
            img.anchor = OneCellAnchor(_from=marker, ext=size)
            ws.add_image(img)

        # Signature: centered in column B, on "Генеральный директор" row
        if dir_row and _SIGNATURE_PATH.exists():
            sig_img = XLImage(str(_SIGNATURE_PATH))
            _add_centered(sig_img, dir_row - 1, 250, 85)

        # Stamp: centered in column B, 2 rows below "М.П."
        if mp_row and _STAMP_PATH.exists():
            stamp_img = XLImage(str(_STAMP_PATH))
            _add_centered(stamp_img, mp_row + 1, 163, 163)

    out = BytesIO()
    wb.save(out)
    return out.getvalue()
