"""Sửa nhãn "Điều N" của các đoạn đã lập chỉ mục từ trước khi `find_articles` được
vá (tài liệu có mục lục bị gán nhãn sai: cả văn bản mang nhãn "Điều 41").

Không cần tệp gốc và không gọi LLM hay nhúng lại: dựng lại văn bản từ chính các đoạn
trong Chroma (theo thứ tự `chunk_id`), dò lại các điều bằng `find_articles` hiện hành,
rồi ghi đè `article_number` và `articles` trong metadata. Vector và văn bản giữ nguyên.

Phần gối đầu giữa hai đoạn liền kề làm văn bản dựng lại có đoạn lặp, nhưng
`find_articles` chỉ nhận số điều tăng dần nên bản lặp không làm lệch nhãn.

    python scripts/fix_article_labels.py --source QuyCheDaoTaoDanSu_Trinh_ky.md            # chỉ xem
    python scripts/fix_article_labels.py --source QuyCheDaoTaoDanSu_Trinh_ky.md --apply    # ghi
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import chromadb  # noqa: E402

from app.pipeline.ingestion import articles_in_span, find_articles  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="tên tệp nguồn, vd. QuyCheDaoTaoDanSu_Trinh_ky.md")
    ap.add_argument("--collection", default="sa_quyche")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--apply", action="store_true", help="ghi vào Chroma (mặc định chỉ in thay đổi)")
    args = ap.parse_args()

    client = chromadb.HttpClient(host=args.host, port=args.port)
    col = client.get_collection(args.collection)
    got = col.get(where={"source": args.source}, include=["documents", "metadatas"])
    rows = sorted(zip(got["ids"], got["documents"], got["metadatas"]), key=lambda r: int(r[2].get("chunk_id", 0)))
    if not rows:
        sys.exit(f"Không có đoạn nào có source={args.source!r} trong {args.collection}")

    # Dựng lại văn bản và ghi lại khoảng [start, end) của từng đoạn.
    full = ""
    spans: list[tuple[int, int]] = []
    for _, text, _ in rows:
        start = len(full)
        full += text + "\n"
        spans.append((start, len(full) - 1))
    articles = find_articles(full)
    print(f"{len(rows)} đoạn; dò được {len(articles)} điều (đầu: {articles[:2]}, cuối: {articles[-1:]})")

    ids, metas, changed = [], [], 0
    for (cid, _, meta), (start, end) in zip(rows, spans):
        covered = articles_in_span(articles, start, end, len(full))
        new_num = covered[0] if covered else ""
        new_list = json.dumps(covered, ensure_ascii=False)
        if meta.get("article_number", "") != new_num or meta.get("articles", "[]") != new_list:
            changed += 1
            if changed <= 8:
                print(f"  chunk {meta.get('chunk_id')}: {meta.get('article_number')!r} -> {new_num!r}")
            meta = dict(meta, article_number=new_num, articles=new_list)
        ids.append(cid)
        metas.append(meta)
    print(f"{changed}/{len(rows)} đoạn đổi nhãn")

    if args.apply and changed:
        for i in range(0, len(ids), 100):
            col.update(ids=ids[i : i + 100], metadatas=metas[i : i + 100])
        print("Đã ghi vào Chroma.")
    elif changed:
        print("(chạy lại với --apply để ghi)")


if __name__ == "__main__":
    main()
