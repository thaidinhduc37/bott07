"""Đồng bộ lại giáo trình giữa PostgreSQL và Chroma (sửa lỗi "lệch: PostgreSQL ghi N đoạn, Qdrant có M điểm").

Nguyên nhân: `ingest_giaotrinh*.py` từng đánh chỉ mục vào Chroma với `document_id = uuid5(tên tệp)` nhưng
tạo `Document` trong PostgreSQL với id ngẫu nhiên, nên hai bên không có id nào trùng (trích dẫn, lọc theo tài liệu,
xóa/lập lại chỉ mục đều hỏng); `ingest_giaotrinh.py` còn nạp cả các tệp không gắn môn nào mà không tạo `Document`.

Script làm hai việc, không xóa điểm vector nào:
  1. Tài liệu đã có trong PostgreSQL: đổi `document_id` trong metadata Chroma từ uuid5 sang id thật.
  2. Điểm mồ côi (có trong Chroma, chưa có `Document`): tạo `Document` (id = uuid5 của tên tệp, không gắn môn)
     + `DocumentVersion` INDEXED, chép tệp nguồn vào storage để lập lại chỉ mục được.

Chạy lại nhiều lần an toàn (idempotent). Mặc định chỉ in kế hoạch; thêm `--apply` để ghi.

    python scripts/fix_chroma_document_ids.py            # xem trước
    python scripts/fix_chroma_document_ids.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import chromadb  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import AsyncSessionLocal  # noqa: E402
from app.models.documents import Document, DocumentVersion  # noqa: E402
from app.models.enums import DocumentType, IndexStatus  # noqa: E402
from app.models.users import User, UserRole  # noqa: E402
from app.services.documents.storage_service import StorageService  # noqa: E402

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus" / "giao-trinh"
MANAGER_EMAIL = "qldt@hvktcnan.edu.vn"


def legacy_id(file_name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"giaotrinh:{file_name}"))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    settings = get_settings()
    col = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port).get_collection(
        settings.collection("giaotrinh")
    )
    got = col.get(include=["metadatas"], limit=100000)
    ids_by_doc: dict[str, list[str]] = {}
    titles: dict[str, str] = {}
    for pid, meta in zip(got["ids"], got["metadatas"]):
        ids_by_doc.setdefault(meta["document_id"], []).append(pid)
        titles[meta["document_id"]] = meta.get("title") or ""
    print(f"Chroma: {len(got['ids'])} điểm, {len(ids_by_doc)} tài liệu")

    by_legacy = {legacy_id(f.name): f for f in CORPUS_DIR.glob("*.md")}

    async with AsyncSessionLocal() as db:
        docs = (
            await db.execute(
                select(Document)
                .options(selectinload(Document.versions))
                .where(Document.document_type == DocumentType.GIAOTRINH)
            )
        ).scalars().all()
        known = {str(d.id) for d in docs}

        # 1. Gắn lại id cho tài liệu đã có Document.
        rekey: list[tuple[str, str]] = []  # (id cũ trong Chroma, id thật)
        for d in docs:
            if str(d.id) in ids_by_doc:
                continue
            names = {v.file_name for v in d.versions}
            # file_name trong DB là tên gốc (xem ingest_giaotrinh_full.py: `stored.file_name`).
            old = next((legacy_id(n) for n in names if legacy_id(n) in ids_by_doc), None)
            if old:
                rekey.append((old, str(d.id)))
        print(f"Gắn lại id: {len(rekey)} tài liệu, {sum(len(ids_by_doc[o]) for o, _ in rekey)} điểm")

        # 2. Điểm mồ côi -> tạo Document.
        handled = {o for o, _ in rekey}
        orphans = [i for i in ids_by_doc if i not in known and i not in handled]
        print(f"Mồ côi (chưa có Document): {len(orphans)} tài liệu, {sum(len(ids_by_doc[i]) for i in orphans)} điểm")
        for oid in orphans:
            src = by_legacy.get(oid)
            print(f"  {oid[:8]} {len(ids_by_doc[oid]):4d} điểm  {titles[oid][:50]}  <- {src.name if src else 'KHÔNG THẤY TỆP NGUỒN'}")

        if not args.apply:
            print("\n(Xem trước — thêm --apply để ghi.)")
            return

        for old, new in rekey:
            pids = ids_by_doc[old]
            for i in range(0, len(pids), 500):
                chunk = pids[i : i + 500]
                col.update(ids=chunk, metadatas=[{"document_id": new}] * len(chunk))

        manager_id = (
            await db.execute(select(User.id).join(UserRole, UserRole.user_id == User.id).where(User.email == MANAGER_EMAIL))
        ).scalar_one()
        storage = StorageService()
        made = 0
        for oid in orphans:
            src = by_legacy.get(oid)
            if src is None:
                print(f"  bỏ qua {oid[:8]}: không có tệp nguồn trong corpus")
                continue
            data = src.read_bytes()
            stored = storage.save(
                data=data, original_filename=src.name, subdir="uploads/documents", accept=[".md"], allow_text=True
            )
            db.add(Document(id=uuid.UUID(oid), title=titles[oid] or src.stem, document_type=DocumentType.GIAOTRINH,
                            course_id=None, uploaded_by_id=manager_id))
            await db.flush()
            db.add(
                DocumentVersion(
                    document_id=uuid.UUID(oid), version=1, file_path=stored.relative_path, file_name=src.name,
                    mime_type=stored.mime_type, file_size=stored.size, file_hash=stored.hash,
                    index_status=IndexStatus.INDEXED, indexed_at=datetime.now(timezone.utc),
                    chunk_count=len(ids_by_doc[oid]),
                )
            )
            made += 1
        await db.commit()
        print(f"Đã gắn lại id {len(rekey)} tài liệu và tạo {made} Document cho điểm mồ côi.")

    after = Counter(m["document_id"] for m in col.get(include=["metadatas"], limit=100000)["metadatas"])
    print(f"Chroma sau khi sửa: {sum(after.values())} điểm, {len(after)} tài liệu")


if __name__ == "__main__":
    asyncio.run(main())
