"""Nạp đầy đủ giáo trình / đề cương từ copus/hoctap/ vào RAG, có gắn môn học
và có bản ghi tài liệu trong PostgreSQL.

Vì sao có tệp này: `scripts/ingest_giaotrinh.py` (bản cũ) chỉ ghi vector vào
Chroma mà không tạo Document/DocumentVersion trong PostgreSQL. Trong khi đó
`ChatService.modes_ready()` đếm số DocumentVersion có index_status=INDEXED để
quyết định mục "Giáo trình & đề cương" có dùng được không. Kết quả: Chroma đã
có vector nhưng PostgreSQL đếm 0, UI hiện "Chưa có tài liệu nào được nạp cho
mục Giáo trình & đề cương".

Tệp này làm cả hai việc đúng như luồng upload chuẩn
(`DocumentsService.upload` + `index_in_background`):

  1. Copy tệp vào server/storage/uploads/documents (đường dẫn hợp lệ cho
     `resolve_under_repo` khi reindex).
  2. Tạo Document (loại GIAOTRINH, gắn course_id, uploaded_by = cán bộ quản lý
     đào tạo) + DocumentVersion.
  3. Chạy pipeline ingest (encoder + reranker + LLM viết ngữ cảnh) vào Chroma.
  4. Đồng bộ DocumentVersion về index_status=INDEXED kèm số trang/đoạn.

Chạy idempotent: mỗi tệp có id deterministic (uuid5 theo tên tệp), chạy lại sẽ
tìm thấy Document cũ và chỉ nạp lại những bản chưa INDEXED. Vì vậy có thể
ngắt giữa chừng rồi chạy lại.

Cách dùng:
    python scripts/ingest_giaotrinh_full.py            # nạp tất cả
    python scripts/ingest_giaotrinh_full.py --limit 5  # chỉ 5 tệp đầu (thử)
    python scripts/ingest_giaotrinh_full.py --no-context  # bỏ bước LLM viết ngữ cảnh
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Thêm server vào path để import được app (đúng như ingest_giaotrinh.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

from app.config import get_settings  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.models.academic import Course  # noqa: E402
from app.models.documents import Document, DocumentVersion  # noqa: E402
from app.models.enums import DocumentType, IndexStatus  # noqa: E402
from app.models.users import User, UserRole  # noqa: E402
from app.pipeline.indexing import IndexingService  # noqa: E402
from app.rag_container import get_rag_container  # noqa: E402
from app.services.storage_service import StorageService  # noqa: E402
from sqlalchemy import select  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingest_giaotrinh_full")

CORPUS_DIR = Path(__file__).resolve().parent.parent / "copus" / "hoctap"

# Cán bộ quản lý đào tạo — người "nạp" tài liệu (uploaded_by_id).
MANAGER_EMAIL = "qldt@hvktcnan.edu.vn"

# Bản đồ tên tệp -> mã môn học. Chỉ các tệp có trong danh sách mới được nạp;
# tệp không khớp (vd. .backup, giáo trình chính trị không có môn trong bảng
# courses) bị bỏ qua an toàn. Muốn nạp thêm, thêm dòng "tên tệp": "MÃ_MÔN".
FILE_TO_COURSE: dict[str, str] = {
    # --- Giáo dục thể chất (PE201) ---
    "20_K5_Giao_duc_the_chat_HP1.md": "PE201",
    "21_K5_Giao_duc_the_chat_HP2.md": "PE201",
    "22_K5_Giao_duc_TC3_Bong_ban.md": "PE201",
    "23_K5_Giao_duc_TC3_Cau_long.md": "PE201",
    # --- Pháp luật đại cương (GE201) ---
    "6_K2_Phap_luat_dai_cuong.md": "GE201",
    # --- Trí tuệ nhân tạo (CS301) ---
    "29_Nhap_mon_cong_nghe_so_va_ung_dung_AI.md": "CS301",
    "39_Hoc_may.md": "CS301",
    "45_Xu_ly_ngon_ngu_tu_nhien_va_thi_giac.md": "CS301",
    "48_Cong_nghe_dien_toan_dam_may.md": "CS301",
    "53_Phat_trien_giai_phap_an_ninh_mang_dua_tren_AI.md": "CS301",
    "60_Bao_mat_IoT.md": "CS301",
    "61_An_toan_mang_di_dong_va_khong_day.md": "CS301",
    # --- Phát triển ứng dụng Web (CS302) ---
    "40_Lap_trinh_Web.md": "CS302",
    "63_An_toan_thuong_mai_dien_tu.md": "CS302",
    # --- Hệ quản trị cơ sở dữ liệu (CS303) ---
    "33_Co_so_du_lieu.md": "CS303",
    "34_He_quan_tri_co_so_du_lieu.md": "CS303",
    # --- An toàn và bảo mật thông tin (CS304) ---
    "38_An_toan_va_bao_mat_he_thong_thong_tin.md": "CS304",
    "41_Lap_trinh_ung_dung_trong_ATTT.md": "CS304",
    "46_He_thong_xac_thuc_sinh_trac_hoc.md": "CS304",
    "47_Phat_trien_phan_mem_an_toan.md": "CS304",
    "50_An_toan_mang_may_tinh.md": "CS304",
    "51_Kiem_thu_va_danh_gia_an_toan_HTTT.md": "CS304",
    "52_Giam_sat_phat_hien_va_ung_cuu_su_co_ATTT.md": "CS304",
    "54_Phan_tich_ma_doc.md": "CS304",
    "55_Dieu_tra_so.md": "CS304",
    "56_Quan_ly_an_toan_thong_tin.md": "CS304",
    "57_Dien_toan_bien.md": "CS304",
    # --- Công nghệ phần mềm (CS305) ---
    "14_K1_Ky_nang_mem.md": "CS305",
    "15_K4_Phuong_phap_NCKH.md": "CS305",
    "15_K4_Vat_ly_dien_ung_dung.md": "CS305",
    "16_K4_Vat_ly_dien_ung_dung.md": "CS305",
    "17_K4_Toi_uu_hoa.md": "CS305",
    "18_K4_Phuong_phap_tinh_CNTT.md": "CS305",
    "35_Phan_tich_thiet_ke_he_thong_thong_tin.md": "CS305",
    "37_Kien_truc_may_tinh_va_hop_ngu.md": "CS305",
    "49_Hoc_sau.md": "CS305",
    "58_Doi_moi_sang_tao_va_tu_duy_khoi_nghiep_Check.md": "CS305",
    "59_Thuc_tap_co_so.md": "CS305",
    # --- Xử lý ngôn ngữ tự nhiên (CS306) ---
    "45_Xu_ly_ngon_ngu_tu_nhien_va_thi_giac.md": "CS306",
}


def _clean_title(filename: str) -> str:
    """'33_Co_so_du_lieu.md' -> 'Co so du lieu'."""
    stem = Path(filename).stem
    if "_" in stem:
        stem = stem.split("_", 1)[1]
    return stem.replace("_", " ").strip()


async def _find_manager_id(db) -> str:
    row = (
        await db.execute(
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .where(User.email == MANAGER_EMAIL)
        )
    ).scalar_one()
    return str(row)


async def _course_map(db) -> dict[str, str]:
    """{mã môn: id môn}."""
    rows = (await db.execute(select(Course.code, Course.id))).all()
    return {code: str(cid) for code, cid in rows}


async def _existing_by_doc_id(db) -> dict[str, Document]:
    """{document.id: document} cho mọi tài liệu GIAOTRINH."""
    rows = (
        await db.execute(select(Document).where(Document.document_type == DocumentType.GIAOTRINH))
    ).scalars().all()
    return {str(d.id): d for d in rows}


def _latest_version(doc: Document) -> DocumentVersion | None:
    if not doc.versions:
        return None
    return max(doc.versions, key=lambda v: v.version)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Chỉ nạp N tệp đầu (0 = tất cả).")
    parser.add_argument(
        "--no-context", action="store_true", help="Tắt bước LLM viết ngữ cảnh (nhanh, rẻ hơn)."
    )
    args = parser.parse_args()

    settings = get_settings()
    if args.no_context:
        settings.use_llm_context = False

    container = get_rag_container()
    indexer = IndexingService(container.models, container.store, container.reader, settings)
    storage = StorageService()

    # Nạp model ngay để biết sớm nếu thiếu RAM.
    t0 = time.time()
    container.models.tokenizer
    log.info("Tokenizer sẵn sàng sau %.1fs", time.time() - t0)

    files = sorted(CORPUS_DIR.glob("*.md"))
    selected = [f for f in files if f.name in FILE_TO_COURSE]
    skipped = [f.name for f in files if f.name not in FILE_TO_COURSE]
    if args.limit > 0:
        selected = selected[: args.limit]

    log.info("Tệp trong corpus: %d | sẽ nạp: %d | bỏ qua (không có môn): %d", len(files), len(selected), len(skipped))
    if skipped:
        log.info("Bỏ qua: %s", ", ".join(sorted(skipped)))
    if not selected:
        log.warning("Không có tệp nào để nạp.")
        return

    ok = fail = 0
    async with AsyncSessionLocal() as db:
        manager_id = await _find_manager_id(db)
        courses = await _course_map(db)
        existing = await _existing_by_doc_id(db)

        for i, f in enumerate(selected, 1):
            name = f.name
            code = FILE_TO_COURSE[name]
            course_id = courses.get(code)
            if course_id is None:
                log.warning("[%d/%d] %s: mã môn %s không có trong bảng courses, bỏ qua", i, len(selected), name, code)
                fail += 1
                continue

            doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"giaotrinh:{name}"))
            title = _clean_title(name)
            data = f.read_bytes()
            file_hash = hashlib.sha256(data).hexdigest()

            # Idempotent: đã có Document này và bản mới nhất đã INDEXED -> bỏ qua.
            doc = existing.get(doc_id)
            if doc is not None:
                latest = _latest_version(doc)
                if latest is not None and latest.index_status == IndexStatus.INDEXED:
                    log.info("[%d/%d] %s: đã INDEXED, bỏ qua", i, len(selected), name)
                    ok += 1
                    continue

            # 1. Copy tệp vào storage (đường dẫn hợp lệ để reindex).
            stored = storage.save(
                data=data,
                original_filename=name,
                subdir="uploads/documents",
                accept=[".md"],
                allow_text=True,
            )

            # 2. Tạo (hoặc lấy lại) Document + DocumentVersion.
            doc = existing.get(doc_id)
            if doc is None:
                doc = Document(
                    title=title,
                    document_type=DocumentType.GIAOTRINH,
                    course_id=course_id,
                    uploaded_by_id=manager_id,
                )
                db.add(doc)
                await db.flush()
                existing[doc_id] = doc
                version_no = 1
            else:
                version_no = (max((v.version for v in doc.versions), default=0)) + 1

            version = DocumentVersion(
                document_id=doc.id,
                version=version_no,
                file_path=stored.relative_path,
                file_name=stored.file_name,
                mime_type=stored.mime_type,
                file_size=stored.size,
                file_hash=stored.hash,
                index_status=IndexStatus.PROCESSING,
            )
            db.add(version)
            await db.commit()
            await db.refresh(version)

            # 3. Chạy pipeline ingest vào Chroma.
            log.info("[%d/%d] Nạp %s -> %s (%s)...", i, len(selected), name, code, title)
            try:
                report = await indexer.ingest(
                    file_path=str(f),
                    document_id=doc_id,
                    document_type="giaotrinh",
                    title=title,
                    course_id=course_id,
                )
            except Exception as e:  # noqa: BLE001
                log.error("[%d/%d] %s: THẤT BẠI: %s", i, len(selected), name, e)
                version.index_status = IndexStatus.FAILED
                version.index_error = str(e)[:2000]
                await db.commit()
                fail += 1
                continue

            # 4. Đồng bộ về INDEXED.
            version.index_status = IndexStatus.INDEXED
            version.indexed_at = datetime.now(timezone.utc)
            version.page_count = report.pages
            version.chunk_count = report.chunks
            version.contextual_count = report.contextualised
            version.index_error = " | ".join(report.warnings) if report.warnings else None
            await db.commit()
            ok += 1
            log.info(
                "[%d/%d] OK %s: %d trang, %d đoạn, %d ngữ cảnh, %.1fs",
                i, len(selected), name, report.pages, report.chunks, report.contextualised, report.seconds,
            )

    log.info("=== XONG === thành công: %d, thất bại: %d", ok, fail)


if __name__ == "__main__":
    asyncio.run(main())
