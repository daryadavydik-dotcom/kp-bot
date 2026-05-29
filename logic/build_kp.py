from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, Side

_PROJECT_ROOT = Path(__file__).parent.parent
_SIGNATURE_PATH = _PROJECT_ROOT / "Подпись.png"
_STAMP_PATH = _PROJECT_ROOT / "Печать.png"
_LOGO_MAIN_PATH = _PROJECT_ROOT / "Главный логотип.png"
_LOGO_RIGHT_PATH = _PROJECT_ROOT / "лого справа.png"
_LOGO_LEFT_TOP_PATH = _PROJECT_ROOT / "лого снизу верхний.png"
_LOGO_LEFT_BOT_PATH = _PROJECT_ROOT / "лого слева нижний.png"

_EMU = 9525  # 1 px in EMU


def _format_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _fmt_num(value) -> str:
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

    company = client.get("client_name", "")
    contact = client.get("contact_person", "")
    if company or contact:
        parts = ["Специалисту"]
        if company:
            parts.append(company)
        if contact:
            parts.append(contact)
        addressee = "\n".join(parts)
    else:
        addressee = ""

    replacements = {
        "kp_number": kp_number,
        "date": _format_date(today),
        "kp_valid_until": _format_date(valid_until),
        "addressee": addressee,
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


def fill_template(template_bytes: bytes, replacements: dict, logos: dict | None = None) -> bytes:
    """Replace all {{key}} placeholders in every cell of every sheet."""
    import re as _re
    wb = openpyxl.load_workbook(BytesIO(template_bytes))

    empty_product_nums = {
        n for n in range(1, 21)
        if not replacements.get(f"product_{n}", "")
    }

    for ws in wb.worksheets:
        # ── Pass 1: locate placeholder positions ─────────────────────────────
        _CLIENT_KEYS = {"addressee"}
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

        # ── Pass 2: replace placeholders ─────────────────────────────────────
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

        # ── Pass 3: formatting ────────────────────────────────────────────────

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

        # Column widths
        ws.column_dimensions["A"].width = 22
        ws.column_dimensions["F"].width = 16

        # Header and client row alignment
        first_product_row = min(product_placeholder_rows.values()) if product_placeholder_rows else 999
        header_end = max(1, first_product_row - 2)
        for row in ws.iter_rows(min_row=1, max_row=header_end):
            for cell in row:
                if cell.value is None:
                    continue
                if cell.row in client_field_rows:
                    cell.alignment = Alignment(horizontal="right", vertical="top", wrap_text=True)
                else:
                    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # Times New Roman 13pt for all non-header rows (rows > 2 are logo+company header)
        # Header = rows 1-11 (logo rows + company text + КП number row)
        # Content starts at row 12 (client row)
        HEADER_END_ROW = 11
        TNR = Font(name="Times New Roman", size=13)
        TNR_BOLD = Font(name="Times New Roman", size=13, bold=True)
        for row in ws.iter_rows(min_row=HEADER_END_ROW + 1):
            for cell in row:
                if cell.value is None:
                    continue
                existing = cell.font
                is_bold = existing and existing.bold
                cell.font = TNR_BOLD if is_bold else TNR

        # Add hyperlinks to cells containing URLs or email addresses
        _URL_RE = _re.compile(r'(?:https?://|www\.)([\w\-./]+)')
        _EMAIL_RE = _re.compile(r'[\w.+-]+@[\w\-]+\.[a-z]{2,}')
        for row in ws.iter_rows(min_row=1, max_row=HEADER_END_ROW):
            for cell in row:
                if not isinstance(cell.value, str):
                    continue
                email_m = _EMAIL_RE.search(cell.value)
                if email_m:
                    cell.hyperlink = f"mailto:{email_m.group(0)}"
                    continue
                url_m = _URL_RE.search(cell.value)
                if url_m:
                    raw = url_m.group(0)
                    cell.hyperlink = raw if raw.startswith("http") else f"http://{raw}"

        # Fix ОКПО row — merge A:F only if it's a standalone row (not in multi-row merge)
        for _row in ws.iter_rows(min_row=1, max_row=HEADER_END_ROW):
            for _cell in _row:
                if isinstance(_cell.value, str) and "ОКПО" in _cell.value:
                    _rn = _cell.row
                    _in_multirow = any(
                        mr.min_row <= _rn <= mr.max_row and mr.min_row != mr.max_row
                        for mr in ws.merged_cells.ranges
                    )
                    if _in_multirow:
                        break
                    _is_full = any(
                        mr.min_row <= _rn <= mr.max_row and mr.min_col == 1 and mr.max_col >= 6
                        for mr in ws.merged_cells.ranges
                    )
                    if not _is_full:
                        try:
                            ws.merge_cells(f"A{_rn}:F{_rn}")
                        except Exception:
                            pass
                    ws.cell(row=_rn, column=1).alignment = Alignment(
                        horizontal="center", vertical="center", wrap_text=True
                    )
                    break

        # Fix Исх. row — single line, no wrap
        for _row in ws.iter_rows(min_row=1, max_row=HEADER_END_ROW):
            for _cell in _row:
                if isinstance(_cell.value, str) and _cell.value.startswith("Исх"):
                    _cell.alignment = Alignment(wrap_text=False, horizontal="left", vertical="center")
                    ws.row_dimensions[_cell.row].height = 15
                    break

        # Fix intro row ("В ответ на") height so text fits
        for _row in ws.iter_rows(min_row=1, max_row=header_end):
            for _cell in _row:
                if isinstance(_cell.value, str) and "В ответ на" in _cell.value:
                    _tlen = len(_cell.value)
                    _lines = max(2, -(-_tlen // 80))
                    ws.row_dimensions[_cell.row].height = _lines * 18
                    break

        # Fix Итого row — thin border on total sum cell (column F)
        _thin = Side(style="thin")
        _sum_border = Border(top=_thin, bottom=_thin, left=_thin, right=_thin)
        for _row in ws.iter_rows():
            for _cell in _row:
                if isinstance(_cell.value, str) and "Итого" in _cell.value:
                    ws.cell(row=_cell.row, column=6).border = _sum_border
                    break
            else:
                continue
            break

        # ── Pass 3.5: partial bold — keyword bold, value after colon normal ─────
        from openpyxl.cell.rich_text import CellRichText, TextBlock
        from openpyxl.cell.text import InlineFont as _IFont

        _SEMI_BOLD = ("• Условия оплаты:", "• Срок изготовления:", "• Способ доставки:")
        _IBOLD = _IFont(b=True, rFont="Times New Roman")
        _INORM = _IFont(b=False, rFont="Times New Roman")

        for _row in ws.iter_rows():
            for _cell in _row:
                if not isinstance(_cell.value, str):
                    continue
                for _pfx in _SEMI_BOLD:
                    if _cell.value.startswith(_pfx):
                        _rest = _cell.value[len(_pfx):]
                        _cell.value = CellRichText(
                            TextBlock(_IBOLD, _pfx),
                            TextBlock(_INORM, _rest),
                        )
                        _cell.font = Font(name="Times New Roman", size=13)
                        break

        # ── Pass 4: delete empty product rows (bottom → top) ─────────────────
        rows_to_delete = sorted(
            [product_placeholder_rows[n] for n in empty_product_nums if n in product_placeholder_rows],
            reverse=True,
        )
        for row_num in rows_to_delete:
            ws.delete_rows(row_num)

        # ── Pass 5: insert logos and images ──────────────────────────────────
        from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
        from openpyxl.drawing.xdr import XDRPositiveSize2D

        logos = logos or {}

        def _get_img(key: str, fallback_path: Path):
            """Return XLImage from logos dict (bytes) or local file, or None."""
            data = logos.get(key)
            if data:
                return XLImage(BytesIO(data))
            if fallback_path.exists():
                return XLImage(str(fallback_path))
            return None

        def _place(img, row_0: int, col_0: int, col_off_px: int, row_off_px: int, w_px: int, h_px: int):
            if img is None:
                return
            marker = AnchorMarker(col=col_0, colOff=col_off_px * _EMU, row=row_0, rowOff=row_off_px * _EMU)
            size = XDRPositiveSize2D(w_px * _EMU, h_px * _EMU)
            img.anchor = OneCellAnchor(_from=marker, ext=size)
            ws.add_image(img)

        # Left-top: 44×57 — col_off_px=120, row_off_px=43 (closer to center, directly above left-bot)
        _place(_get_img("left_top", _LOGO_LEFT_TOP_PATH), row_0=0, col_0=0, col_off_px=120, row_off_px=43, w_px=44, h_px=57)
        # Left-bottom: 90×68 (+15%) — col_off_px=97 (center aligned with left-top center at 142px)
        _place(_get_img("left_bot", _LOGO_LEFT_BOT_PATH), row_0=1, col_0=0, col_off_px=97, row_off_px=0, w_px=90, h_px=68)
        # Main logo: 551×90 (+15%) — col B+0px, shifted left
        _place(_get_img("main", _LOGO_MAIN_PATH), row_0=0, col_0=1, col_off_px=0, row_off_px=3, w_px=551, h_px=90)
        # Right logo: 108×120 (+30%) — col E+4px (2/3 in col E, 1/3 in col F); bottom at 3rd-from-bottom text line
        _place(_get_img("right", _LOGO_RIGHT_PATH), row_0=0, col_0=4, col_off_px=4, row_off_px=37, w_px=108, h_px=120)

        # Find anchor rows for signature and stamp
        dir_row = None
        mp_row = None
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    if dir_row is None and "директор" in cell.value.lower():
                        dir_row = cell.row
                    if mp_row is None and "м.п" in cell.value.lower():
                        mp_row = cell.row

        def _add_centered(img, row_0based, img_w, img_h):
            col_b_width_px = 336
            offset_px = max(0, (col_b_width_px - img_w) // 2)
            marker = AnchorMarker(col=1, colOff=offset_px * _EMU, row=row_0based, rowOff=0)
            size = XDRPositiveSize2D(img_w * _EMU, img_h * _EMU)
            img.anchor = OneCellAnchor(_from=marker, ext=size)
            ws.add_image(img)

        if dir_row and _SIGNATURE_PATH.exists():
            sig_img = XLImage(str(_SIGNATURE_PATH))
            _add_centered(sig_img, dir_row - 1, 250, 85)

        if mp_row and _STAMP_PATH.exists():
            stamp_img = XLImage(str(_STAMP_PATH))
            _add_centered(stamp_img, mp_row + 1, 163, 163)

        # ── Pass 6: merge rows 1-4 into single block; text sits just below logos ─
        _HMERGE_END = 3   # A1:F3 — text sits just below main logo (~93px)
        _HTEXT_END = 8    # company text lives in rows 3-8
        _hdr_lines = []
        for _rn in range(3, _HTEXT_END + 1):
            _hc = ws.cell(row=_rn, column=1)
            if isinstance(_hc.value, str) and _hc.value.strip():
                _hdr_lines.append(_hc.value.strip())

        _already_hmerged = any(
            mr.min_row == 1 and mr.max_row >= _HMERGE_END
            for mr in ws.merged_cells.ranges
        )
        if not _already_hmerged and _hdr_lines:
            for _mr in list(ws.merged_cells.ranges):
                if _mr.min_row >= 1 and _mr.max_row <= _HTEXT_END:
                    ws.unmerge_cells(str(_mr))
            ws.merge_cells(f"A1:F{_HMERGE_END}")
            ws.cell(row=1, column=1).value = "\n".join(_hdr_lines)
            ws.cell(row=1, column=1).alignment = Alignment(
                horizontal="center", vertical="bottom", wrap_text=True
            )
            ws.cell(row=1, column=1).font = Font(name="Times New Roman", size=9, bold=True, italic=True)
            # Collapse rows 5-8 so they leave no blank gap
            for _rn in range(_HMERGE_END + 1, _HTEXT_END + 1):
                ws.row_dimensions[_rn].hidden = True

    out = BytesIO()
    wb.save(out)
    return out.getvalue()
