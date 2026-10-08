"""Dựng DOCX bằng `python-docx`, không dùng tệp mẫu: mọi biểu mẫu được dựng bằng mã theo một `FormLayout` trong `form_layouts.py`.

Trình bày theo Nghị định 30/2020/NĐ-CP (Phụ lục I, Mẫu 1.1) và đơn gốc trong `data/nguon/mau-don`: A4, lề trên và dưới 20mm,
trái 30mm, phải 15mm, Times New Roman 14pt (13pt cho đầu trang và khối chữ ký), giãn dòng 1.15, đoạn thân căn đều thụt đầu
dòng 1.27cm.

Điểm vào: `render_form(layout, data, slots)` trả byte .docx. `data` là dữ liệu đơn đã gộp (profileSnapshot phủ bởi formData, do
bên gọi làm) với mọi giá trị đã là chuỗi hiển thị; module chỉ thay `Seg(f=...)` nguyên văn. `slots` là danh sách cột chữ ký
theo thứ tự do bên gọi dựng (xem `SignatureSlot`).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from docx.table import Table

from app.services.forms.form_layouts import BodyLine, FormLayout, Seg, TableBlock

FONT_NAME = "Times New Roman"
FONT_SIZE = Pt(14)
# Phần đầu văn bản (tên cơ quan, quốc hiệu, tiêu ngữ, địa danh) đều 13pt — đúng tệp mẫu đã chỉnh; Nghị định 30: 12–14.
MASTHEAD_SIZE = Pt(13)
MOTTO_SIZE = Pt(13)
CAPTION_SIZE = Pt(11)
# Giãn dòng đơn; giữa các đoạn cách 6pt; dòng đầu đoạn thụt 1 cm (Nghị định 30: thụt 1–1,27 cm).
LINE_SPACING = 1.0
FIRST_LINE_INDENT = Cm(1.0)
PARA_GAP = Pt(6)
# "Kính gửi:" thụt 3,25 cm; các nơi nhận gạch đầu dòng thụt 5 cm (đúng vị trí trong tệp mẫu đã chỉnh).
RECIPIENT_INDENT = Cm(3.25)
RECIPIENT_ITEM_INDENT = Cm(5.0)
# Khổ A4, lề 20/20/30/15 mm (Nghị định 30: trên-dưới 20–25, trái 30–35, phải 15–20); vùng chữ rộng 21 - 3 - 1,5 = 16,5 cm.
TEXT_WIDTH_CM = 16.5

# Dòng 0 là cơ quan chủ quản trực tiếp (không in đậm); các dòng sau là tên
# đơn vị ban hành văn bản (in đậm, có gạch chân bên dưới) — đúng thể thức
# Mẫu 1.1 Phụ lục I, Nghị định 30/2020/NĐ-CP.
_AGENCY_SUPERIOR_LINE = "BỘ CÔNG AN"
_AGENCY_LINES = ["HỌC VIỆN KỸ THUẬT", "VÀ CÔNG NGHỆ AN NINH"]
_NATION_LINE_1 = "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"
_NATION_LINE_2 = "Độc lập - Tự do - Hạnh phúc"
# Độ dài gạch chân xấp xỉ 1/3-1/2 độ dài dòng chữ phía trên, theo thể thức.
_AGENCY_UNDERLINE = "_" * 18

# Dấu phiên bản của bộ dựng, ghi vào thuộc tính tệp (Comments). Đổi giá trị này mỗi khi định dạng đơn thay đổi:
# đơn CHƯA KÝ có tệp mang dấu cũ sẽ được dựng lại khi mở xem (xem `FormsService.file_of`); đơn đã ký thì không
# bao giờ bị dựng lại vì tệp đã gắn với chữ ký.
RENDERER_VERSION = "nd30-2026-10-06"


def docx_renderer_version(path) -> str | None:
    """Dấu phiên bản của một tệp .docx do hệ thống dựng; None nếu không đọc được hoặc không có dấu."""
    try:
        return Document(str(path)).core_properties.comments or None
    except Exception:
        return None


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
    style.paragraph_format.line_spacing = LINE_SPACING
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.space_after = Pt(0)


def _page_numbers(document: Document) -> None:
    """Đánh số trang từ trang 2 (Nghị định 30, Phụ lục I): chữ số Ả Rập, 13–14pt, đứng, canh giữa theo chiều
    ngang trong lề trên; trang đầu không hiện số. Đơn một trang thì phần này không xuất hiện gì."""
    section = document.sections[0]
    section.different_first_page_header_footer = True
    p = section.header.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = _run(p, "", size=FONT_SIZE)
    for kind, text in (("begin", None), (None, " PAGE "), ("end", None)):
        if kind:
            el = run._r.makeelement(qn("w:fldChar"), {qn("w:fldCharType"): kind})
        else:
            el = run._r.makeelement(qn("w:instrText"), {})
            el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            el.text = text
        run._r.append(el)


def _set_margins(document: Document) -> None:
    section = document.sections[0]
    # python-docx mặc định khổ Letter; văn bản hành chính dùng A4.
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(3.0)
    section.right_margin = Cm(1.5)


def _run(
    paragraph,
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
    size: Pt | None = None,
):
    r = paragraph.add_run(text)
    r.font.name = FONT_NAME
    r.font.size = size or FONT_SIZE
    r.bold = bold
    r.italic = italic
    r.underline = underline
    rpr = r._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), FONT_NAME)
    return r


def _rule(cell, cell_width_cm: float, line_width_cm: float) -> None:
    """Đường kẻ ngang nét liền, căn giữa trong ô, dài `line_width_cm` (Nghị định 30: dưới tên cơ quan ban hành
    và dưới tiêu ngữ). Là viền dưới của một đoạn rỗng thụt hai bên — không dùng dãy dấu gạch dưới, vì dãy
    ký tự lệch theo phông và cỡ chữ."""
    p = cell.add_paragraph()
    side = Cm(max(cell_width_cm - line_width_cm, 0) / 2)
    p.paragraph_format.left_indent = side
    p.paragraph_format.right_indent = side
    p.paragraph_format.space_before = Pt(3)   # chừa khoảng cách để đường kẻ không áp sát chân chữ
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = Pt(2)
    ppr = p._p.get_or_add_pPr()
    borders = ppr.makeelement(qn("w:pBdr"), {})
    bottom = borders.makeelement(
        qn("w:bottom"), {qn("w:val"): "single", qn("w:sz"): "6", qn("w:space"): "1", qn("w:color"): "auto"}
    )
    borders.append(bottom)
    ppr.append(borders)


def _no_borders(table: Table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.makeelement(qn("w:tblBorders"), {})
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = borders.makeelement(qn(f"w:{edge}"), {qn("w:val"): "none", qn("w:sz"): "0", qn("w:space"): "0"})
        borders.append(el)
    tbl_pr.append(borders)


_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$")


def _vn_date(text: str) -> str:
    """Ngày dạng ISO ("2005-09-02") in theo thể thức Việt Nam ("02/09/2005"); chuỗi khác giữ nguyên."""
    m = _ISO_DATE.match(text.strip())
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else text


def _resolve_value(field_key: str, data: dict) -> str:
    v = data.get(field_key)
    if v is None:
        return ""
    return _vn_date(str(v))


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
    left_cm, right_cm = 6.0, 10.5   # tổng = bề rộng vùng chữ A4 (21 - 3 - 1,5 = 16,5 cm); quốc hiệu 13pt cần ≥ 10 cm để nằm một dòng
    left_w, right_w = Cm(left_cm), Cm(right_cm)
    table.columns[0].width = left_w
    table.columns[1].width = right_w

    left, right = table.rows[0].cells
    left.width = left_w
    right.width = right_w

    p_superior = left.paragraphs[0]
    p_superior.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p_superior, _AGENCY_SUPERIOR_LINE, size=MASTHEAD_SIZE)

    for line in _AGENCY_LINES:
        p = left.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(p, line, bold=True, size=MASTHEAD_SIZE)
    # Đường kẻ dưới tên cơ quan: dài 1/3 – 1/2 độ dài dòng tên (Nghị định 30, Phụ lục I); dòng "VÀ CÔNG NGHỆ AN NINH"
    # dài khoảng 5,3 cm ở 13pt nên lấy 2,4 cm.
    _rule(left, left_cm, 2.4)

    p1 = right.paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p1, _NATION_LINE_1, bold=True, size=MASTHEAD_SIZE)

    # Tiêu ngữ: chữ thường đứng đậm; đường kẻ ngay dưới, dài đúng độ dài dòng chữ.
    p2 = right.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p2, _NATION_LINE_2, bold=True, size=MOTTO_SIZE)
    _rule(right, right_cm, 5.6)

    # Địa danh, ngày tháng năm: chữ nghiêng, cách đường kẻ một khoảng.
    p3 = right.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p3.paragraph_format.space_before = Pt(8)
    _run(
        p3,
        f"Bắc Ninh, ngày {submission_date.day:02d} tháng {submission_date.month:02d} năm {submission_date.year}",
        italic=True,
        size=MOTTO_SIZE,
    )


# ------------------------------------------------------------------ title

def _title(document: Document, layout: FormLayout, data: dict) -> None:
    p = document.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(0 if layout.subtitle else 12)
    p.paragraph_format.keep_with_next = True
    _run(p, layout.title, bold=True)

    if layout.subtitle:
        p2 = document.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p2.paragraph_format.space_after = Pt(12)
        p2.paragraph_format.keep_with_next = True
        if isinstance(layout.subtitle, str):
            _run(p2, layout.subtitle, italic=True)
        else:
            for seg in layout.subtitle:
                if seg.t is not None:
                    _run(p2, seg.t, italic=True)
                elif seg.f is not None:
                    _run(p2, _resolve_value(seg.f, data), italic=True, bold=True)


# -------------------------------------------------------------- recipients

def _recipients(document: Document, layout: FormLayout, data: dict) -> None:
    """"Kính gửi:" (đậm) thụt 3,25 cm; mỗi nơi nhận một dòng gạch đầu dòng thụt sâu thêm 1 cm, không dấu
    câu cuối dòng — đúng tệp mẫu đã chỉnh."""

    p = document.add_paragraph()
    p.paragraph_format.left_indent = RECIPIENT_INDENT
    p.paragraph_format.keep_with_next = True
    _run(p, "Kính gửi:", bold=True)

    last = len(layout.recipients) - 1
    rp = p
    for i, r in enumerate(layout.recipients):
        rp = document.add_paragraph()
        rp.paragraph_format.left_indent = RECIPIENT_ITEM_INDENT
        rp.paragraph_format.keep_with_next = i != last
        _run(rp, "- ")
        if isinstance(r, str):
            _run(rp, r.rstrip(";. "))
        else:
            for seg in r:
                if seg.t is not None:
                    _run(rp, seg.t)
                elif seg.f is not None:
                    _run(rp, _resolve_value(seg.f, data), bold=True)
    rp.paragraph_format.space_after = Pt(12)


# -------------------------------------------------------------------- body

def _body_paragraph(document: Document):
    """Đoạn văn bản chính: căn đều hai bên, dòng đầu thụt 1 cm, cách đoạn sau 6pt."""
    p = document.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = FIRST_LINE_INDENT
    p.paragraph_format.space_after = PARA_GAP
    return p


def _body_line(document: Document, line: BodyLine, data: dict) -> None:
    if line.only_if is not None and not data.get(line.only_if):
        return

    pieces, extra_paragraphs = _seg_line_text_and_multiline(line.segs, data)

    p = _body_paragraph(document)
    for text, is_fill in pieces:
        _run(p, text, bold=is_fill)

    for extra in extra_paragraphs:
        ep = _body_paragraph(document)
        ep.paragraph_format.first_line_indent = Cm(0)
        _run(ep, extra, bold=True)


# Cột STT cố định hẹp; các cột còn lại chia phần dư của vùng chữ, riêng cột
# đầu (tên học phần) rộng gấp đôi. Tổng luôn bằng bề rộng vùng chữ.
_STT_WIDTH_CM = 1.5


def _data_table(document: Document, block: TableBlock, data: dict) -> None:
    raw_rows = data.get(block.rows_key) or []
    if not isinstance(raw_rows, list):
        raw_rows = []
    n_rows = max(len(raw_rows), block.min_rows)
    n_rows = min(n_rows, block.max_rows)

    table = document.add_table(rows=1 + n_rows, cols=1 + len(block.columns))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    weights = [2.0 if i == 0 else 1.0 for i in range(len(block.columns))]
    rest = TEXT_WIDTH_CM - _STT_WIDTH_CM
    widths = [Cm(_STT_WIDTH_CM)] + [Cm(rest * w / sum(weights)) for w in weights]
    for col, w in zip(table.columns, widths):
        col.width = w

    def _fill(cell, text: str, *, bold: bool = False, center: bool = True) -> None:
        cp = cell.paragraphs[0]
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
        cp.paragraph_format.space_before = Pt(2)
        cp.paragraph_format.space_after = Pt(2)
        _run(cp, text, bold=bold)

    header = table.rows[0].cells
    for cell, w in zip(header, widths):
        cell.width = w
    _fill(header[0], "STT", bold=True)
    for ci, col in enumerate(block.columns, start=1):
        _fill(header[ci], col.label, bold=True)
    # Dòng tiêu đề lặp lại nếu bảng sang trang mới.
    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    tr_pr.append(tr_pr.makeelement(qn("w:tblHeader"), {}))

    for ri in range(n_rows):
        row_cells = table.rows[ri + 1].cells
        for cell, w in zip(row_cells, widths):
            cell.width = w
        # STT is always auto-numbered here, never trusted from client data.
        _fill(row_cells[0], str(ri + 1))

        row_data = raw_rows[ri] if ri < len(raw_rows) and isinstance(raw_rows[ri], dict) else {}
        for ci, col in enumerate(block.columns, start=1):
            _fill(row_cells[ci], str(row_data.get(col.key) or ""), center=ci != 1)

    gap = document.add_paragraph()
    gap.paragraph_format.space_after = Pt(6)


def _body(document: Document, layout: FormLayout, data: dict) -> None:
    for line in layout.lines:
        if isinstance(line, TableBlock):
            _data_table(document, line, data)
        else:
            _body_line(document, line, data)


# ------------------------------------------------------------- signatures

_BOLD_FONT_CANDIDATES = (
    "C:/Windows/Fonts/timesbd.ttf",                                            # Windows: Times New Roman Bold
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",           # Linux: số đo giống Times New Roman
    "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Bold.ttf",
)


def _bold_text_width_cm(text: str, size_pt: float) -> float | None:
    """Bề rộng (cm) của `text` in đậm ở cỡ `size_pt`, đo bằng phông Times thật; None nếu máy không có phông nào."""
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    for path in _BOLD_FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(path, 100)
        except OSError:
            continue
        return font.getlength(text) / 100 * size_pt / 72 * 2.54
    return None


def _title_wraps(title: str, cell_width_cm: float) -> bool:
    """Tiêu đề cột ký có xuống hai dòng trong ô rộng `cell_width_cm` không (trừ lề ô mặc định 0,19 cm mỗi bên)?"""
    width = _bold_text_width_cm(title, MASTHEAD_SIZE.pt)
    if width is None:
        return len(title) > 17   # không đo được: ước lượng theo số ký tự
    return width > cell_width_cm - 0.38


def _signature_table(document: Document, slots: list[SignatureSlot]) -> None:
    if not slots:
        return
    table = document.add_table(rows=1, cols=len(slots))
    _no_borders(table)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    col_width = Cm(TEXT_WIDTH_CM / max(len(slots), 1))
    for col in table.columns:
        col.width = col_width
    # Khối chữ ký không bị cắt đôi giữa hai trang.
    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    tr_pr.append(tr_pr.makeelement(qn("w:cantSplit"), {}))

    # Tiêu đề dài (vd "LĐ PHÒNG QLĐT&BDNC") xuống hai dòng trong cột 5,5 cm. Khi đó các tiêu đề ngắn được đẩy xuống một dòng để dòng
    # "(Ký và ghi rõ họ tên)" và vùng chữ ký của mọi cột vẫn thẳng hàng.
    title_wraps = any(_title_wraps(slot.title, TEXT_WIDTH_CM / max(len(slots), 1)) for slot in slots)

    for cell, slot in zip(table.rows[0].cells, slots):
        cell.width = col_width
        p_title = cell.paragraphs[0]
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_title.paragraph_format.keep_with_next = True
        if title_wraps and not _title_wraps(slot.title, TEXT_WIDTH_CM / max(len(slots), 1)):
            p_title.paragraph_format.space_before = Pt(16)
        _run(p_title, slot.title, bold=True, size=MASTHEAD_SIZE)

        p_caption = cell.add_paragraph()
        p_caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(p_caption, _SIGNATURE_CAPTION, italic=True, size=CAPTION_SIZE)

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
            _run(p_name, slot.signed_by, bold=True, size=MASTHEAD_SIZE)
            if slot.signed_at:
                p_time = cell.add_paragraph()
                p_time.alignment = WD_ALIGN_PARAGRAPH.CENTER
                ts = slot.signed_at
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                # Giờ ký theo giờ Việt Nam (trước đây in giờ UTC: 09:23 thay vì 16:23).
                ts = ts.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
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
    document.core_properties.comments = RENDERER_VERSION
    _set_default_font(document)
    _set_margins(document)
    _page_numbers(document)

    # Ngày ghi trên đơn là ngày theo giờ Việt Nam (22h giờ Việt Nam vẫn là ngày hôm đó, không phải ngày UTC).
    submission_date = (submission_date or datetime.now(timezone.utc)).astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))

    _masthead(document, submission_date)
    _title(document, layout, data)
    _recipients(document, layout, data)
    _body(document, layout, data)
    spacer = document.add_paragraph()
    spacer.paragraph_format.keep_with_next = True
    _signature_table(document, slots)

    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()
