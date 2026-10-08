# Trợ lý ảo hỗ trợ sinh viên

MVP cho Học viện Kỹ thuật và Công nghệ An ninh: hỏi đáp quy chế và giáo trình bằng RAG **có trích dẫn
kiểm chứng được**, lịch học – lịch thi, ôn tập bằng câu hỏi trắc nghiệm, biểu mẫu hành chính tự động điền,
ký điện tử nội bộ và trình ký qua luồng phê duyệt hai cấp, cùng quản lý đào tạo (khoa, lớp, môn, phòng,
thời khóa biểu, điểm).

Chữ ký trong hệ thống là **chữ ký điện tử nội bộ** (mã băm + nhật ký), không phải chữ ký số công cộng theo
quy định về chứng thư số. Giao diện nói rõ điều này ở những trang liên quan.

## Ba lớp chống bịa của trợ lý

1. **Cổng abstention đã calibrate (τ).** Điểm cross-encoder cao nhất thấp hơn τ thì từ chối *trước khi*
   gọi mô hình ngôn ngữ.
2. **Chấm đủ bằng chứng, viết lại truy vấn.** Đoạn văn yếu thì viết lại truy vấn và tìm lại.
3. **Kiểm chứng groundedness.** Từng khẳng định được đối chiếu lại với đoạn văn trước khi trả về.

Đổi corpus thì phải calibrate lại τ. Bộ câu hỏi và kết quả đánh giá nằm ở `data/danh-gia/`
(`run_eval.py`).

## Kiến trúc

```text
React/Vite (5173) ──► FastAPI (5000, tiền tố /api) ──┬──► PostgreSQL (5433, Docker)
                       pipeline RAG chạy cùng tiến trình ├──► ChromaDB (8001, Docker)
                                                         ├──► storage/ trên đĩa
                                                         └──► LLM: Gemini
```

Pipeline là bản port CPU của [`notebooks/rag-pipeline-2026.ipynb`](notebooks/rag-pipeline-2026.ipynb):
hybrid retrieval (BGE-M3 dense ∥ BM25 + pyvi → RRF) → cross-encoder rerank → cổng abstention → vòng
retrieve–grade–rewrite → sinh câu trả lời có trích dẫn → kiểm chứng groundedness.

## Cấu trúc thư mục

```text
client/                 React 19 + Vite 6 + TypeScript — giao diện ba nhóm người dùng
  src/styles/           CSS thuần, chia theo vùng (base, layout, shell, chat, ...) rồi theo tính năng
server/
  main.py               điểm vào (python main.py)
  app/
    core/               cấu hình, phiên DB, phụ thuộc xác thực, bảo mật
    models/ schemas/    mô hình SQLAlchemy / kiểu Pydantic (camelCase)
    routers/            HTTP + phân quyền
    services/           logic nghiệp vụ theo lĩnh vực:
                          academic/  danh mục, khoa, phòng, lịch, điểm
                          accounts/  đăng nhập, người dùng, nhật ký, bảng điều khiển
                          chat/      hội thoại và cầu nối tới pipeline
                          documents/ tài liệu và lưu trữ tệp
                          forms/     biểu mẫu, bản in .docx, phê duyệt, chữ ký
                          learning/  ôn tập, sổ tay, kế hoạch thi, tiến độ, phản hồi
    pipeline/           pipeline RAG và kho vector
  alembic/              migration
  storage/              sinh lúc chạy: tệp tải lên, đơn đã dựng, ảnh chữ ký
data/
  nguon/                bản gốc (giáo trình, quy chế, mẫu đơn, mẫu CSV lịch)
  corpus/               bản đã chuẩn hóa cho RAG (giao-trinh, quy-che-quy-dinh, tkb, ...)
  danh-gia/             bộ đánh giá RAG
  bao-cao/              tài liệu mô tả hệ thống
  support.json          nội dung trang Hỗ trợ (sửa không cần đụng mã)
scripts/                nạp corpus, kiểm tra, và scripts/test/ (bộ nghiệm thu gọi API thật)
notebooks/              notebook nghiên cứu pipeline
```

## Cài đặt

Yêu cầu: Docker Desktop đang chạy, Node.js ≥ 22.19, Python 3.11.

```bash
cp server/.env.example server/.env   # điền GEMINI_API_KEY; không bao giờ commit .env
npm install                          # phần client
npm run infra:up                     # PostgreSQL + ChromaDB
npm run db:migrate                   # alembic upgrade head
npm run db:seed                      # dữ liệu demo
```

Môi trường Python nằm ở `server/.venv` (torch CPU cần index riêng — xem `server/Dockerfile`).

## Chạy

```bash
npm run dev:server    # FastAPI :5000   (cd server && .venv/Scripts/python main.py)
npm run dev:web       # Vite :5173
```

Hoặc chạy `bat-len.bat` (Windows): bật Docker, PostgreSQL, ChromaDB, backend, giao diện web rồi mở trình
duyệt. Sau khi sửa backend phải khởi động lại API; Vite tự nạp lại phần client.

Truy cập bằng `http://localhost:5173`, **không** dùng `127.0.0.1` (CORS chỉ cho phép `localhost:5173`).

Nạp tài liệu vào RAG: `python scripts/ingest_giaotrinh_full.py` (giáo trình) — chỉ loại `QUYCHE` và
`GIAOTRINH` được lập chỉ mục.

## Tài khoản demo

Mật khẩu `Demo@2026`, mã PIN ký `135790`, đuôi `@hvktcnan.edu.vn`.

| Tài khoản | Vai trò |
|---|---|
| `admin@` | Quản trị viên |
| `qldt@` | Quản lý đào tạo (duyệt cấp hai, nạp lịch, điểm, tài liệu) |
| `khoa@` | Trưởng khoa (chỉ thấy khoa mình phụ trách) |
| `gv.*@` | Giảng viên |
| `sv.*@` | Học viên |

## Kiểm thử

`scripts/test/` gồm các bộ nghiệm thu gọi API đang chạy và Postgres trong Docker (`sa-postgres-dev`):

```bash
python scripts/test/test_catalog.py          # một bộ
pwsh scripts/test/chay-tat-ca.ps1            # tất cả (cần PowerShell 7)
```

Giới hạn tần suất (đăng nhập 5 lần/phút theo email, thao tác đã đăng nhập theo người dùng) được hàm `login()` của bộ test tự dọn nên các
bộ chạy liền nhau được. Dữ liệu thử có tiền tố `ZT`/`zt-` và được dọn sau mỗi lần chạy, kể cả khi lỗi. Kiểm tra giao diện: `npm run build:web` (gồm
type-check) và `npm --prefix client run lint`.

## Những chỗ dễ vấp

- **Cổng 5433.** PostgreSQL map ra 5433 trên máy chủ vì 5432 thường đã bị chiếm; trong mạng Docker vẫn là 5432.
- **`.env` không được commit.** Chỉ commit `server/.env.example`.
- **Bản in đơn theo Nghị định 30/2020/NĐ-CP (Phụ lục I).** Đổi bố cục thì tăng `RENDERER_VERSION` trong
  `server/app/services/forms/docx_renderer.py`: bản nháp cũ sẽ được dựng lại khi mở, bản đã ký thì không.
- **Số liệu học tập cho giảng viên chỉ ở dạng tổng hợp** (từ 2 học viên), không có tên hay mã.
