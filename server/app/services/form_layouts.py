"""Print specs for the 7 demo administrative forms.

Reconstructed directly from the ORIGINAL source documents at
`server/data/thutuchanhchinh/*.doc(x)` — extracted verbatim via `antiword`
(the `.doc` files) and `python-docx` (`don-hoc-cai-thien.docx`) — rather than
from the (now-deleted) NestJS `form-layouts.ts`, which itself was a port of
these same source documents. Wording, recipients, and field order below are
copied faithfully from those originals; blanks in the original paper form
(the "……………" fill-in lines) become `Seg(f=<field key>)` references resolved
against the submission's merged profile-snapshot + form-data at render time.

This module is a pure print spec — no DB/business logic. `layout_for(code)`
is the single lookup used by `docx_renderer.render_form()`.

Deviations from the literal source, called out explicitly:
- Every form's signature block is normalised to the shared renderer's fixed
  "(Ký, ghi rõ họ tên)" caption (the originals vary between "Ký, ghi rõ họ tên"
  and "Ký và ghi rõ họ tên"; Nghị định 30/2020/NĐ-CP uses the former) — the
  renderer builds one signature row shape for all forms, matching the
  architecture described in the porting notes (signatureTable() is shared
  code, not per-template).
- `DON_XIN_NGHI_HOC` add an optional `courseCode` line (flagged in the
  porting notes as an optional field on this template) even though the
  original paper form has no dedicated blank for it — shown only when
  present (`only_if`).
- `DON_HOC_CAI_THIEN` additionally surfaces `hocKy`/`namHoc`/
  `soHocPhanDaThi`/`soHocPhanChuaDat` as scalar fields (visible as blanks in
  the original paragraph) even though the porting notes describe this
  template as "only the repeating table field" — the paragraph text in the
  source document plainly has these blanks, so they are kept as fields
  rather than dropped silently.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Seg:
    """One inline fragment of a body line: either literal text (`t`) or a
    reference into the merged submission data (`f`). Exactly one is set.
    `multiline=True` means the field's value is split on newlines into its
    own paragraphs (used for free-text reason/lyDo fields)."""

    t: str | None = None
    f: str | None = None
    multiline: bool = False


def lit(text: str) -> Seg:
    return Seg(t=text)


def fill(field_key: str, *, multiline: bool = False) -> Seg:
    return Seg(f=field_key, multiline=multiline)


@dataclass(frozen=True)
class BodyLine:
    segs: list[Seg]
    before: int = 0
    after: int = 0
    indent_first: bool = False
    # Field key: line is suppressed entirely when this field is falsy/absent
    # in the merged data. None = always rendered.
    only_if: str | None = None


@dataclass(frozen=True)
class TableColumn:
    key: str
    label: str


@dataclass(frozen=True)
class TableBlock:
    rows_key: str
    columns: list[TableColumn]
    min_rows: int = 2
    max_rows: int = 20


@dataclass(frozen=True)
class FormLayout:
    code: str
    title: str
    # Static string, OR a Seg list for a fill-in inside the subtitle (only
    # DON_XIN_HOC_LAI's "(Lần thứ: ……)" needs the latter).
    subtitle: str | list[Seg] | None
    recipients: list[str | list[Seg]]
    lines: list[BodyLine | TableBlock]


# --------------------------------------------------------- identity blocks
#
# Three shared "identity block" fragments, verified against the original
# documents: each of the 7 forms uses exactly one of these verbatim.

NGHI_HOC_1_3_IDENTITY: list[BodyLine] = [
    BodyLine([lit("Tên em là: "), fill("fullName"), lit(" Sinh ngày: "), fill("dateOfBirth")]),
    BodyLine([lit("Là học viên lớp: "), fill("className"), lit(" Khóa: "), fill("cohort")]),
    BodyLine([lit("Mã số học viên: "), fill("studentCode"), lit(" Số điện thoại: "), fill("phone")]),
    BodyLine([lit("Hệ đào tạo: "), fill("trainingSystem")]),
]

DAY_DU_IDENTITY: list[BodyLine] = [
    BodyLine([lit("Họ và tên: "), fill("fullName"), lit(" Sinh ngày: "), fill("dateOfBirth")]),
    BodyLine([lit("Học viên lớp: "), fill("className"), lit(" Khóa: "), fill("cohort")]),
    BodyLine([lit("Mã số học viên: "), fill("studentCode"), lit("; Số điện thoại: "), fill("phone")]),
    BodyLine([lit("Hệ đào tạo: "), fill("trainingSystem")]),
]

HOAN_THI_IDENTITY: list[BodyLine] = [
    BodyLine([lit("Họ và tên: "), fill("fullName")]),
    BodyLine([lit("Sinh ngày: "), fill("dateOfBirth"), lit("; Học viên lớp: "), fill("className")]),
    BodyLine([lit("Mã số học viên: "), fill("studentCode"), lit("; Số điện thoại: "), fill("phone")]),
]

_CAM_ON = BodyLine([lit("Em xin chân thành cảm ơn./.")])


# ---------------------------------------------------------------- layouts

_LAYOUTS: dict[str, FormLayout] = {
    "DON_XIN_NGHI_HOC": FormLayout(
        code="DON_XIN_NGHI_HOC",
        title="ĐƠN XIN PHÉP NGHỈ HỌC",
        subtitle="(Áp dụng cho những trường hợp xin nghỉ từ 01 - 03 ngày)",
        recipients=["Lãnh đạo Phòng QLĐT&BDNC", "Lãnh đạo Phòng Quản lý học viên", "Giáo viên giảng dạy"],
        lines=[
            *NGHI_HOC_1_3_IDENTITY,
            BodyLine([lit("Em viết đơn này xin phép được nghỉ học từ ngày: "), fill("leaveFrom"),
                      lit(" đến ngày "), fill("leaveTo")]),
            BodyLine([lit("Học phần liên quan (nếu có): "), fill("courseCode")], only_if="courseCode"),
            BodyLine([lit("Lý do: "), fill("reason", multiline=True)]),
            BodyLine([lit("Em xin hứa sẽ chép bài, học bài đầy đủ và chấp hành tốt các quy định của Học viện")]),
            BodyLine([lit("Kính mong các thầy cô quan tâm, cho phép em được nghỉ học thời gian trên.")]),
            _CAM_ON,
        ],
    ),
    "DON_XIN_NGHI_HOC_TREN_3": FormLayout(
        code="DON_XIN_NGHI_HOC_TREN_3",
        title="ĐƠN XIN NGHỈ HỌC",
        subtitle=None,
        recipients=[
            "Ban Giám đốc",
            "Lãnh đạo Phòng QLĐT&BDNC",
            "Lãnh đạo Phòng Quản lý học viên",
            "Giáo viên giảng dạy",
        ],
        lines=[
            *DAY_DU_IDENTITY,
            BodyLine([lit("Em viết đơn này xin phép được nghỉ học từ ngày: "), fill("leaveFrom"),
                      lit(" đến ngày "), fill("leaveTo")]),
            BodyLine([lit("Lý do: "), fill("reason", multiline=True)]),
            BodyLine([lit("Em xin hứa sẽ chép bài, học bài đầy đủ và chấp hành tốt các quy định của Học viện.")]),
            BodyLine([lit("Kính mong các thầy cô quan tâm, cho phép em được nghỉ học thời gian trên.")]),
            _CAM_ON,
        ],
    ),
    "DON_XIN_HOAN_THI": FormLayout(
        code="DON_XIN_HOAN_THI",
        title="ĐƠN XIN HOÃN THI KẾT THÚC HỌC PHẦN",
        subtitle=None,
        recipients=["Lãnh đạo Phòng QLĐT&BDNC", "Lãnh đạo Phòng Quản lý học viên"],
        lines=[
            *HOAN_THI_IDENTITY,
            BodyLine([lit("Theo kế hoạch thi hết học phần của Học viện, học kỳ "), fill("hocKy"),
                      lit(", năm học "), fill("namHoc"), lit(" ngày "), fill("ngayThi"),
                      lit(" em sẽ dự thi học phần: "), fill("hocPhan")]),
            BodyLine([lit("Em không thể tham gia thi học phần theo lịch của Học viện, lý do: "),
                      fill("lyDo", multiline=True)]),
            BodyLine([lit(
                "Em làm đơn này kính mong phòng QLĐT&BDNC, phòng Quản lý học viên cho phép em được hoãn "
                "thi học phần trên và bố trí cho em được dự thi vào buổi thi khác để em hoàn thiện điểm "
                "theo quy chế quy định."
            )]),
            _CAM_ON,
        ],
    ),
    "DON_BO_SUNG_LI_DO_HOAN_THI": FormLayout(
        code="DON_BO_SUNG_LI_DO_HOAN_THI",
        title="ĐƠN XIN THI BỔ SUNG",
        subtitle=None,
        recipients=["Lãnh đạo Phòng QLĐT&BDNC", "Lãnh đạo Phòng Quản lý học viên"],
        lines=[
            *HOAN_THI_IDENTITY,
            BodyLine([lit("Em đã có đơn xin hoãn thi kết thúc học phần: "), fill("hocPhan"),
                      lit(" ngày thi "), fill("ngayThi"), lit(" và được Học viện đồng ý.")]),
            BodyLine([lit(
                "Nay em đã bố trí được thời gian thi, em làm đơn này kính mong phòng Quản lý đào tạo xem "
                "xét sắp xếp lịch cho em được thi bổ sung vào thời gian sớm nhất có thể để em hoàn thiện "
                "điểm theo quy chế quy định."
            )]),
            _CAM_ON,
        ],
    ),
    "DON_XIN_HOC_LAI": FormLayout(
        code="DON_XIN_HOC_LAI",
        title="ĐƠN XIN HỌC LẠI",
        subtitle=[lit("(Lần thứ: "), fill("lanThuMayXinHoc"), lit(")")],
        recipients=["Lãnh đạo Phòng QLĐT&BDNC", "Lãnh đạo Phòng Quản lý học viên"],
        lines=[
            *DAY_DU_IDENTITY,
            BodyLine([lit("Em đã tham gia thi kết thúc học phần: "), fill("hocPhan")]),
            BodyLine([lit("Lần thi: "), fill("lanThi"), lit(", lần học: "), fill("lanHoc"),
                      lit(". Điểm thi của em đạt được là: "), fill("diemThi"), lit(" điểm.")]),
            BodyLine([lit(
                "Kết quả điểm học phần của em vẫn chưa đạt yêu cầu theo quy định. Em viết đơn này kính "
                "mong Lãnh đạo Phòng Quản lý đào tạo và bồi dưỡng nâng cao, Lãnh đạo phòng Quản lý học "
                "viên xem xét sắp xếp lịch cho em được học lại các học phần trên theo đúng quy chế, quy "
                "định."
            )]),
            BodyLine([lit(
                "Em xin cam đoan thực hiện nghiêm túc quy định của Học viện và nộp đầy đủ kinh phí học "
                "lại theo quy định."
            )]),
            _CAM_ON,
        ],
    ),
    "DON_XIN_HOC_BO_SUNG": FormLayout(
        code="DON_XIN_HOC_BO_SUNG",
        title="ĐƠN XIN HỌC BỔ SUNG",
        subtitle=None,
        recipients=[
            "Lãnh đạo Phòng Quản lý đào tạo và bồi dưỡng nâng cao",
            "Lãnh đạo Phòng Quản lý học viên",
            [lit("Lãnh đạo Khoa "), fill("tenKhoa")],
        ],
        lines=[
            *DAY_DU_IDENTITY,
            BodyLine([lit("Căn cứ lịch học tập học phần: "), fill("hocPhan")]),
            BodyLine([lit("Tổng số tiết (tín chỉ) quy định: "), fill("soTietQuyDinh"),
                      lit(" em đã học được số tiết: "), fill("soTietDaHoc")]),
            BodyLine([lit("Em không tham gia học số tiết: "), fill("soTietNghi"),
                      lit(" vượt quá 20% so với quy định.")]),
            BodyLine([lit("Lý do nghỉ không tham gia học đầy đủ số tiết theo quy định là: "),
                      fill("lyDo", multiline=True)]),
            BodyLine([lit(
                "Em viết đơn này kính mong Lãnh đạo Phòng Quản lý đào tạo và bồi dưỡng nâng cao, Lãnh đạo "
                "Khoa và Lãnh đạo phòng Quản lý học viên xem xét bố trí cho em được học bổ sung kiến thức "
                "còn thiếu để em đủ điều kiện tham dự thi kết thúc học phần."
            )]),
            BodyLine([lit(
                "Em xin cam đoan thực hiện nghiêm túc quy định của Học viện và nộp đầy đủ kinh phí học bổ "
                "sung theo quy định."
            )]),
            _CAM_ON,
        ],
    ),
    "DON_HOC_CAI_THIEN": FormLayout(
        code="DON_HOC_CAI_THIEN",
        title="ĐƠN XIN HỌC, THI CẢI THIỆN",
        subtitle=None,
        recipients=["Lãnh đạo Phòng Quản lý đào tạo và bồi dưỡng nâng cao", "Lãnh đạo Phòng Quản lý học viên"],
        lines=[
            *DAY_DU_IDENTITY,
            BodyLine([
                lit("Trong học kỳ "), fill("hocKy"), lit(" năm học "), fill("namHoc"),
                lit(", em đã dự thi kết thúc "), fill("soHocPhanDaThi"),
                lit(" học phần, tuy nhiên có "), fill("soHocPhanChuaDat"),
                lit(
                    " học phần chưa đạt kết quả như mong muốn. Căn cứ Hướng dẫn học, thi cải thiện kết "
                    "quả học tập của Học viện, em viết đơn này kính mong Phòng Quản lý đào tạo và bồi "
                    "dưỡng nâng cao, Phòng Quản lý học viên tạo điều kiện sắp xếp cho em được học, thi "
                    "cải thiện các học phần sau:"
                ),
            ]),
            TableBlock(
                rows_key="hocPhanList",
                columns=[
                    TableColumn("tenHocPhan", "Tên học phần"),
                    TableColumn("soTinChi", "Số tín chỉ"),
                    TableColumn("diemDaDat", "Điểm học phần đã đạt được"),
                ],
                min_rows=2,
                max_rows=20,
            ),
            BodyLine([lit(
                "Em xin cam đoan thực hiện nghiêm túc quy định về học tập của Học viện và nộp đầy đủ kinh "
                "phí học, thi cải thiện theo quy định."
            )]),
            _CAM_ON,
        ],
    ),
}


def layout_for(code: str) -> FormLayout:
    layout = _LAYOUTS.get(code)
    if layout is None:
        raise KeyError(f'Không có bản in cho mẫu đơn "{code}"')
    return layout


def all_codes() -> list[str]:
    return list(_LAYOUTS.keys())
