"""Sửa tên tài liệu mất dấu tiếng Việt — ở PostgreSQL, Chroma và lịch sử trích dẫn.

Nguyên nhân: tên tài liệu từng suy từ tên tệp ("33_Co_so_du_lieu.md" ->
"Co so du lieu"). Tên đúng lấy từ dòng "Tên học phần" trong đề cương (xem
`doc_titles.py`). Script chỉ đổi TÊN — không đụng nội dung chunk, không tính lại
vector, không gọi LLM, nên chạy được cả khi khóa API hỏng và chạy lại bao nhiêu
lần cũng an toàn (idempotent).

    python scripts/fix_document_titles.py --dry-run     # chỉ liệt kê thay đổi
    python scripts/fix_document_titles.py               # áp dụng

Áp dụng ở ba nơi:
  1. `documents.title`  — trang Tài liệu, kế hoạch ôn thi ("Đọc và ôn: …").
  2. Chroma `title` + `prefix` của từng chunk — trích dẫn trong câu trả lời.
  3. `chat_citations.document_title` — trích dẫn của các cuộc hội thoại đã có.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8", errors="replace")

from doc_titles import KNOWN_FIXES, display_title  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

import app.models  # noqa: E402,F401  (đăng ký mọi model cho SQLAlchemy)
from app.db import AsyncSessionLocal  # noqa: E402
from app.models.documents import Document, DocumentVersion  # noqa: E402
from app.rag_container import get_rag_container  # noqa: E402

CORPUS_DIR = ROOT / "copus" / "hoctap"


def new_title_for(old_title: str, filename: str | None) -> str:
    """Tên mới cho một tài liệu; trả lại `old_title` nếu không có gì để sửa."""
    if old_title in KNOWN_FIXES:
        return KNOWN_FIXES[old_title]
    # Chỉ tệp có trong kho giáo trình mới sửa được; tài liệu khác (quy chế tải lên
    # với tên đã đúng) giữ nguyên.
    if filename and (CORPUS_DIR / Path(filename).name).exists():
        return display_title(filename, corpus_dir=CORPUS_DIR)
    return old_title


async def fix_postgres(dry: bool) -> dict[str, str]:
    """documents.title (+ chat_citations). Trả về {tên cũ: tên mới} đã đổi."""
    changed: dict[str, str] = {}
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Document))).scalars().all()
        for d in rows:
            latest = (
                await db.execute(
                    select(DocumentVersion.file_name)
                    .where(DocumentVersion.document_id == d.id)
                    .order_by(DocumentVersion.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            new = new_title_for(d.title, latest)
            if new != d.title:
                print(f"  PG  {d.title!r:58} -> {new!r}")
                changed[d.title] = new
                if not dry:
                    d.title = new
        cited = 0
        for old, new in changed.items():
            if dry:
                n = (await db.execute(text("select count(*) from chat_citations where document_title = :o"), {"o": old})).scalar_one()
            else:
                n = (await db.execute(text("update chat_citations set document_title = :n where document_title = :o"), {"n": new, "o": old})).rowcount
            cited += n or 0
        if not dry:
            await db.commit()
        print(f"  -> {len(changed)} tài liệu, {cited} trích dẫn đã lưu")
    return changed


def fix_chroma(dry: bool) -> None:
    store = get_rag_container().store
    for name in ("sa_giaotrinh", "sa_quyche"):
        try:
            col = store.client.get_collection(name)
        except Exception:  # noqa: BLE001 — bộ sưu tập chưa tồn tại
            continue
        total, changed_titles, chunks = col.count(), {}, 0
        for off in range(0, total, 500):
            batch = col.get(limit=500, offset=off, include=["metadatas"])
            ids, metas = [], []
            for cid, m in zip(batch["ids"], batch["metadatas"]):
                old = m.get("title") or ""
                new = new_title_for(old, m.get("source"))
                if new == old:
                    continue
                changed_titles[old] = new
                m = dict(m)
                m["title"] = new
                # `prefix` bắt đầu bằng "[<tên> | trang N | …" — đổi tên ở đầu, phần còn lại giữ nguyên.
                if isinstance(m.get("prefix"), str) and m["prefix"].startswith(f"[{old}"):
                    m["prefix"] = f"[{new}" + m["prefix"][len(old) + 1:]
                ids.append(cid)
                metas.append(m)
            chunks += len(ids)
            if ids and not dry:
                col.update(ids=ids, metadatas=metas)
        for o, n in list(changed_titles.items())[:60]:
            print(f"  {name[3:8]}  {o!r:58} -> {n!r}")
        print(f"  -> {name}: {len(changed_titles)} tài liệu, {chunks} chunk")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="chỉ liệt kê, không ghi")
    args = ap.parse_args()
    print(("[CHẠY THỬ] " if args.dry_run else "") + "PostgreSQL:")
    await fix_postgres(args.dry_run)
    print("\nChroma:")
    fix_chroma(args.dry_run)
    print("\nXong." if not args.dry_run else "\nChưa ghi gì (--dry-run).")


if __name__ == "__main__":
    asyncio.run(main())
