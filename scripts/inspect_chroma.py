"""Kiểm tra metadata Chroma: phân bố course_id + llm_context (chạy một lần)."""
import chromadb

c = chromadb.HttpClient(
    host="localhost", port=8001, settings=chromadb.config.Settings(anonymized_telemetry=False)
)
col = c.get_collection("sa_giaotrinh", embedding_function=None)
tot = col.count()
print("total sa_giaotrinh:", tot)

# Quét toàn bộ để thống kê course_id (collection dev nhỏ, ~1844 điểm).
from collections import Counter
course_counter = Counter()
ctx_counter = Counter()
offset = 0
BATCH = 256
while True:
    r = col.get(limit=BATCH, offset=offset, include=["metadatas"])
    metas = r["metadatas"]
    if not metas:
        break
    for m in metas:
        course_counter[m.get("course_id") or "(rỗng)"] += 1
        ctx_counter["có_ctx" if (m.get("llm_context") or "").strip() else "không_ctx"] += 1
    if len(metas) < BATCH:
        break
    offset += BATCH

print("course_id distribution:")
for k, v in sorted(course_counter.items(), key=lambda x: -x[1]):
    print(f"   {k}: {v}")
print("llm_context:", dict(ctx_counter))
