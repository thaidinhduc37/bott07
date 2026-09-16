"""`python-docx`-based DOCX builder — port of the (now-deleted) NestJS
`docx-renderer.service.ts`. No template files are used (there never were
any — `server/storage/templates/` is empty); every form is built purely in
code against a `FormLayout` from `form_layouts.py`.

Layout follows Nghị định 30/2020/NĐ-CP formatting conventions: margins top
20mm / bottom 20mm / left 30mm / right 15mm, Times New Roman 13pt body text.

Entry point: `render_form(layout, data, slots)` -> raw .docx bytes.
`data` is the submission's merged data (profileSnapshot overlaid by
formData — the caller's job, not this module's) with every value already a
display-ready string (dates already dd/mm/yyyy, etc — this module does no
type coercion, it only substitutes `Seg(f=...)` references literally).
`slots` is the ordered list of signature columns (built by the caller from
the approval flow + owner) — see `SignatureSlot` below.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timezone

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from docx.table import Table

from app.services.form_layouts import BodyLine, FormLayout, Seg, TableBlock

FONT_NAME = "Times New Roman"
FONT_SIZE = Pt(13)

_AGENCY_LINES = ["BỘ CÔNG AN", "HỌC VIỆN KỸ THUẬT", "VÀ CÔNG NGHỆ AN NINH"]
_NATION_LINE_1 = "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"
_NATION_LINE_2 = "Độc lập - Tự do - Hạnh phúc"

OWNER_SIGNATURE_TITLE = "HỌC VIÊN VIẾT ĐƠN"
_SIGNATURE_CAPTION = "(Ký và ghi rõ họ tên)"


@dataclass
class SignatureSlot:
    """One column of the signature row at the bottom of the document.

    `signed=False` renders a blank spacer of the same height as a real
    signature image, so the unsigned and signed documents have an identical
    layout (no reflow when a signature is later embedded) — this is
    intentional, not an oversight.
    """

    title: str
    signed: bool = False
    image_bytes: bytes | None = None
    signed_by: str | None = None
    signed_at: datetime | None = None


def _set_default_font(document: Document) -> None:
    style = document.styles["Normal"]
    style.font.name = FONT_NAME
    style.font.size = FONT_SIZE
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    for attr in ("w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), FONT_NAME)


def _set_margins(document: Document) -> None:
    section = document.sections[0]
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(3.0)
    section.right_margin = Cm(1.5)


def _run(paragraph, text: str, *, bold: bool = False, italic: bool = False, size: Pt | None = None):
    r = paragraph.add_run(text)
    r.font.name = FONT_NAME
    r.font.size = size or FONT_SIZE
    r.bold = bold
    r.italic = italic
    rpr = r._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), FONT_NAME)
    return r


def _no_borders(table: Table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.makeelement(qn("w:tblBorders"), {})
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = borders.makeelement(qn(f"w:{edge}"), {qn("w:val"): "none", qn("w:sz"): "0", qn("w:space"): "0"})
        borders.append(el)
    tbl_pr.append(borders)


def _resolve_value(field_key: str, data: dict) -> str:
    v = data.get(field_key)
    if v is None:
        return ""
    return str(v)


def _seg_line_text_and_multiline(segs: list[Seg], data: dict) -> tuple[list[tuple[str, bool]], list[str]]:
    """Split a BodyLine's segs into (a) the pieces that render on the first
    paragraph and (b) any additional paragraphs needed for a multiline field
    embedded in the line (reason/lyDo). Returns ([(text, is_fill), ...],
    [extra_paragraph_text, ...])."""

    first_line_pieces: list[tuple[str, bool]] = []
    extra_paragraphs: list[str] = []
    for seg in segs:
        if seg.t is not None:
            first_line_pieces.append((seg.t, False))
        elif seg.f is not None:
            value = _resolve_value(seg.f, data)
            if seg.multiline and "\n" in value:
                parts = value.split("\n")
                first_line_pieces.append((parts[0], True))
                extra_paragraphs.extend(parts[1:])
            else:
                first_line_pieces.append((value, True))
    return first_line_pieces, extra_paragraphs


# --------------------------------------------------------------- masthead

def _masthead(document: Document, submission_date: datetime) -> None:
    table = document.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _no_borders(table)
    table.columns[0].width = Cm(7.5)
    table.columns[1].width = Cm(8.0)

    left, right = table.rows[0].cells

    for i, line in enumerate(_AGENCY_LINES):
        p = left.paragraphs[0] if i == 0 else left.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(p, line, bold=True)

    p1 = right.paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p1, _NATION_LINE_1, bold=True)

    p2 = right.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p2, _NATION_LINE_2, bold=True)

    p3 = right.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(
        p3,
        f"Bắc Ninh, ngày {submission_date.day:02d} tháng {submission_date.month:02d} năm {submission_date.year}",
        italic=True,
    )


# ------------------------------------------------------------------ title

def _title(document: Document, layout: FormLayout, data: dict) -> None:
    document.add_paragraph()
    p = document.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p, layout.title, bold=True, size=Pt(14))

    if layout.subtitle:
        p2 = document.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if isinstance(layout.subtitle, str):
            _run(p2, layout.subtitle, italic=True)
        else:
            for seg in layout.subtitle:
                if seg.t is not None:
                    _run(p2, seg.t, italic=True)
                elif seg.f is not None:
                    _run(p2, _resolve_value(seg.f, data), italic=True, bold=True)
    document.add_paragraph()


# -------------------------------------------------------------- recipients

def _recipients(document: Document, layout: FormLayout, data: dict) -> None:
    p = document.add_paragraph()
    _run(p, "Kính gửi:", bold=True)

    for r in layout.recipients:
        rp = document.add_paragraph()
        rp.paragraph_format.left_indent = Cm(1.0)
        _run(rp, "- ")
        if isinstance(r, str):
            _run(rp, r)
        else:
            for seg in r:
                if seg.t is not None:
                    _run(rp, seg.t)
                elif seg.f is not None:
                    _run(rp, _resolve_value(seg.f, data), bold=True)
    document.add_paragraph()


# -------------------------------------------------------------------- body

def _body_line(document: Document, line: BodyLine, data: dict) -> None:
    if line.only_if is not None and not data.get(line.only_if):
        return

    pieces, extra_paragraphs = _seg_line_text_and_multiline(line.segs, data)

    for _ in range(line.before):
        document.add_paragraph()

    p = document.add_paragraph()
    if line.indent_first:
        p.paragraph_format.first_line_indent = Cm(1.0)
    p.paragraph_format.space_after = Pt(0)
    for text, is_fill in pieces:
        _run(p, text, bold=is_fill)

    for extra in extra_paragraphs:
        ep = document.add_paragraph()
        ep.paragraph_format.space_after = Pt(0)
        _run(ep, extra, bold=True)

    for _ in range(line.after):
        document.add_paragraph()


def _data_table(document: Document, block: TableBlock, data: dict) -> None:
    raw_rows = data.get(block.rows_key) or []
    if not isinstance(raw_rows, list):
        raw_rows = []
    n_rows = max(len(raw_rows), block.min_rows)
    n_rows = min(n_rows, block.max_rows)

    table = document.add_table(rows=1 + n_rows, cols=1 + len(block.columns))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    header = table.rows[0].cells
    hp = header[0].paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(hp, "STT", bold=True)
    for ci, col in enumerate(block.columns, start=1):
        hp = header[ci].paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(hp, col.label, bold=True)

    for ri in range(n_rows):
        row_cells = table.rows[ri + 1].cells
        stt_p = row_cells[0].paragraphs[0]
        stt_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        # STT is always auto-numbered here, never trusted from client data.
        _run(stt_p, str(ri + 1))

        row_data = raw_rows[ri] if ri < len(raw_rows) and isinstance(raw_rows[ri], dict) else {}
        for ci, col in enumerate(block.columns, start=1):
            cp = row_cells[ci].paragraphs[0]
            _run(cp, str(row_data.get(col.key) or ""))

    document.add_paragraph()


def _body(document: Document, layout: FormLayout, data: dict) -> None:
    for line in layout.lines:
        if isinstance(line, TableBlock):
            _data_table(document, line, data)
        else:
            _body_line(document, line, data)


# ------------------------------------------------------------- signatures

def _signature_table(document: Document, slots: list[SignatureSlot]) -> None:
    if not slots:
        return
    table = document.add_table(rows=1, cols=len(slots))
    _no_borders(table)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    col_width = Cm(15.5 / max(len(slots), 1))
    for col in table.columns:
        col.width = col_width

    for cell, slot in zip(table.rows[0].cells, slots):
        cell.width = col_width
        p_title = cell.paragraphs[0]
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(p_title, slot.title, bold=True)

        p_caption = cell.add_paragraph()
        p_caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(p_caption, _SIGNATURE_CAPTION, italic=True, size=Pt(11))

        p_mark = cell.add_paragraph()
        p_mark.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if slot.signed and slot.image_bytes:
            run = p_mark.add_run()
            run.add_picture(io.BytesIO(slot.image_bytes), width=Cm(3.4), height=Cm(1.45))
        else:
            # Blank spacer of the same height as a signature image, so the
            # unsigned and signed documents don't reflow differently.
            p_mark.paragraph_format.space_after = Cm(1.45)

        p_name = cell.add_paragraph()
        p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if slot.signed and slot.signed_by:
            _run(p_name, slot.signed_by, bold=True)
            if slot.signed_at:
                p_time = cell.add_paragraph()
                p_time.alignment = WD_ALIGN_PARAGRAPH.CENTER
                ts = slot.signed_at
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                _run(p_time, f"Ký lúc {ts.strftime('%H:%M %d/%m/%Y')}", italic=True, size=Pt(10))


# --------------------------------------------------------------- entrypoint

def render_form(
    layout: FormLayout,
    data: dict,
    slots: list[SignatureSlot],
    *,
    submission_date: datetime | None = None,
) -> bytes:
    document = Document()
    _set_default_font(document)
    _set_margins(document)

    submission_date = submission_date or datetime.now(timezone.utc)

    _masthead(document, submission_date)
    _title(document, layout, data)
    _recipients(document, layout, data)
    _body(document, layout, data)
    document.add_paragraph()
    _signature_table(document, slots)

    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()
