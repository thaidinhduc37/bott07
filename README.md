# Trợ lý ảo hỗ trợ sinh viên

MVP tích hợp cho Học viện Kỹ thuật và Công nghệ An ninh: hỏi đáp quy chế và giáo trình bằng RAG
**có trích dẫn kiểm chứng được**, xem lịch học – lịch thi, lập biểu mẫu hành chính tự động điền,
ký điện tử nội bộ và trình ký qua luồng phê duyệt hai cấp.

> Trạng thái: **v0.1.0-mvp**. Kế hoạch gốc: [`ke_hoach_trien_khai_14_ngay.md`](ke_hoach_trien_khai_14_ngay.md).

---

## Điều làm hệ thống này khác một bản RAG thông thường

Một pipeline RAG ngây thơ (nhúng → lấy top-k → nhét vào prompt) rất dễ dựng và rất khó tin. Với
tra cứu quy chế, một điều khoản bịa ra trông y hệt một điều khoản có thật. Hệ thống này có **ba
lớp chống bịa độc lập**:

1. **Cổng abstention đã calibrate.** Nếu điểm cross-encoder cao nhất thấp hơn τ, pipeline từ chối
   *trước khi mô hình ngôn ngữ được gọi*. Đây không phải quyết định sinh văn bản nên không thể bị
   thuyết phục. τ được **fit trên tập calibration và báo cáo trên tập held-out**, không đoán bằng tay.
2. **Chấm bằng chứng và viết lại truy vấn.** Trên ngưỡng nhưng đoạn văn vẫn yếu thì viết lại truy
   vấn và tìm lại, thay vì cố trả lời bằng thứ đang có.
3. **Kiểm chứng groundedness.** Từng khẳng định trong câu trả lời được đối chiếu lại với đoạn văn
   trước khi tới tay người dùng.

Kết quả calibrate trên corpus hiện tại: **τ = 0.030**, tách biệt 100% giữa câu trong và ngoài phạm
vi, held-out precision 1.000, **0 trong 14 câu không có căn cứ được trả lời**.

Chữ ký trong hệ thống là **chữ ký điện tử nội bộ**: có mã băm trước/sau và nhật ký đầy đủ, nhưng
không phải chữ ký số công cộng theo quy định về chứng thư số. Giao diện nói rõ điều này ở chân
mọi trang.

---

## Kiến trúc

```text
React/Vite (5173) ──► NestJS API (5000) ──┬──► PostgreSQL (5433)
                                          ├──► storage/ trên đĩa
                                          └──► FastAPI RAG (8000) ──┬──► Qdrant (6333)
                                                                    └──► LLM (Gemini)
```

RAG service là bản port CPU của [`notebooks/rag-pipeline-2026.ipynb`](notebooks/rag-pipeline-2026.ipynb):
hybrid retrieval (BGE-M3 dense ∥ BM25 + pyvi → RRF) → cross-encoder rerank (int8) → cổng abstention
→ vòng lặp retrieve–grade–rewrite → sinh câu trả lời có trích dẫn → kiểm chứng groundedness.

| Yêu cầu | Số đo thực tế |
|---|---|
| Máy 16 GB, không GPU | Toàn hệ thống chiếm **1.83 GB** (`scripts/test/do-ram.ps1`) |
| Độ trễ truy vấn | trung vị **20.4 s** (rerank int8, CANDIDATES_K=12) |
| Chống bịa | 0/14 câu không có căn cứ được trả lời |

---

## Cài đặt

Yêu cầu: Docker Desktop đang chạy, Node.js ≥ 22.19, Python 3.11.

```bash
cp .env.example .env       # rồi điền GEMINI_API_KEY
npm install                # workspace client và server/api
npm run infra:up           # PostgreSQL + Qdrant
npm run db:migrate         # tạo schema
npm run db:seed            # dữ liệu demo từ CSV thật
```

RAG service dùng venv riêng vì torch CPU cần index URL riêng:

```bash
cd server/rag-service
python -m venv .venv
.venv/Scripts/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/pip install -r requirements.txt
python ../../scripts/download_models.py    # tải BGE-M3 + reranker (~2.5 GB)
```

Nạp corpus vào chỉ mục tìm kiếm và calibrate ngưỡng:

```bash
python scripts/ingest_corpus.py --only quyche
python scripts/calibrate_tau.py            # rồi cập nhật ANSWER_THRESHOLD trong .env
```

> `ingest_corpus.py` lấy id tài liệu **từ PostgreSQL**, nên phải chạy `db:seed` trước.
> Đổi corpus thì **phải calibrate lại τ** — một τ cũ hoặc từ chối oan, hoặc bắt đầu bịa.

## Chạy

```bash
npm run chay
```

Một lệnh, lo hết: bật Docker Desktop nếu chưa chạy, dựng PostgreSQL + Qdrant,
rồi lần lượt rag-service → API → web, và mở trình duyệt. Mỗi dịch vụ nằm trong
một cửa sổ riêng có tiêu đề `sa · <tên>` để khi hỏng thì biết nhìn log ở đâu.

| Tham số | Dùng khi |
|---|---|
| *(không có)* | Đang phát triển — sửa mã là tự nạp lại |
| `-- -SanPham` | Trình bày — chạy bản đã build, khởi động nhanh và nhẹ hơn |
| `-- -ChiHaTang` | Chỉ cần PostgreSQL + Qdrant, tự chạy tay các phần còn lại |

```bash
npm run dung                 # dừng web/api/rag, giữ PostgreSQL + Qdrant
npm run dung -- -CaHaTang    # dừng luôn hạ tầng
```

Kịch bản **chờ từng lớp thật sự trả lời** rồi mới sang lớp sau, không ngủ vài
giây rồi hy vọng. Thứ tự này quan trọng vì khởi động sai thứ tự làm lỗi hiện ra
ở chỗ khác với chỗ hỏng: API không nối được PostgreSQL sẽ báo lỗi ở màn hình
đăng nhập, và người ta đi tìm lỗi ở phần xác thực.

Lần chạy đầu, rag-service mất khoảng một phút vì phải nạp hai mô hình lên RAM.

**Vào bằng `localhost`, không phải `127.0.0.1`** — CORS của API chỉ nhận
`localhost:5173`, vào bằng IP sẽ không đăng nhập được.

<details>
<summary>Chạy tay từng dịch vụ</summary>

| Dịch vụ | Lệnh | Cổng |
|---|---|---:|
| Hạ tầng | `npm run infra:up` | 5433 / 6333 |
| RAG service | `cd server/rag-service && .venv/Scripts/python -m uvicorn app.main:app --port 8000` | 8000 |
| API | `npm run dev:api` | 5000 |
| Web | `npm run dev:web` | 5173 |

</details>

### Chạy toàn bộ trong Docker

Hai môi trường tách biệt, mỗi cái khởi động bằng đúng một lệnh:

```bash
npm run docker:dev     # phát triển: hot-reload, mã nguồn bind-mount từ host
npm run docker:prod    # production: build tối ưu, giống hệt triển khai thật
```

Lần đầu chạy `docker:dev`, database `sa-postgres-data-dev` còn trống — chạy `npm run db:migrate &&
npm run db:seed` (từ host, giống hệt bước "Cài đặt" ở trên) để có schema và tài khoản demo trước khi
đăng nhập được. Postgres của dev expose ra cùng cổng host với production nên lệnh chạy từ host luôn
trỏ đúng vào Postgres đang chạy tại thời điểm đó.

Dừng lại: `npm run docker:dev:down` hoặc `npm run docker:prod:down` (đúng file đã dùng để chạy).

`docker:dev` dựng cả 5 service (Postgres, Qdrant, web, api, rag-service) trong container, sửa code
trên host là container tự nạp lại (Vite HMR / Nest watch / uvicorn `--reload`) — không thay
`scripts/chay.ps1` (chạy trực tiếp trên host, nhanh hơn vì không qua Docker), chỉ là một lựa chọn
cộng thêm khi cần môi trường nhất quán hoặc không muốn cài Node/Python trên máy.

Dữ liệu Postgres/Qdrant của `docker:dev` và `docker:prod` nằm trên **volume khác nhau** — không
trộn lẫn dữ liệu thử nghiệm vào dữ liệu triển khai.

Hai điều cần biết trước khi chạy `docker:prod` (áp dụng cả `docker:dev`):

- **Mô hình không nằm trong image.** BGE-M3 và cross-encoder cộng lại ~2.5 GB. Chúng nằm trong
  volume `sa-models` (dùng chung cho cả hai môi trường), tải một lần ở lần chạy đầu — nên container
  rag-service mất khá lâu mới `healthy`. Muốn tránh: chạy `scripts/download_models.py` trên host
  trước rồi gắn cache vào.
- **`JWT_ACCESS_SECRET` và `JWT_REFRESH_SECRET` là bắt buộc.** Compose sẽ từ chối khởi động nếu
  chúng trống, thay vì chạy với một khóa mặc định mà không ai để ý.

## Tài khoản demo

Mật khẩu `Demo@2026`, mã PIN ký `135790`.

| Email | Vai trò | Dùng để xem |
|---|---|---|
| `admin@hvktcnan.edu.vn` | Quản trị viên | Tài khoản, nhật ký, trạng thái dịch vụ, tài liệu |
| `qldt@hvktcnan.edu.vn` | Quản lý đào tạo | Cấp duyệt **thứ hai**, nạp lịch, tài liệu |
| `qlhv@hvktcnan.edu.vn` | Cán bộ phê duyệt | Cấp duyệt **thứ nhất** |
| `gv.lehoanganh@hvktcnan.edu.vn` | Giáo viên + phê duyệt | Tài liệu giảng dạy |
| `sv.nguyenducanh@hvktcnan.edu.vn` | Học viên (B3D15001) | Toàn bộ luồng của học viên |
| `sv.tranthimai@hvktcnan.edu.vn` | Học viên (B3D15002) | Dùng để thử IDOR |

## Kiểm thử

```bash
pwsh scripts/test/chay-tat-ca.ps1      # toàn bộ bộ nghiệm thu
pwsh scripts/test/do-ram.ps1           # đo RAM toàn hệ thống
```

| Bộ | Nội dung | Kết quả |
|---|---|---|
| `test-auth-rbac.ps1` | Xác thực, phân quyền | 36/36 |
| `test-refresh-rotation.ps1` | Xoay refresh token, phát hiện tái dùng | 8/8 |
| `test_rag_pipeline.py` | Truy xuất, cổng abstention | 35/35 |
| `test-forms.ps1` | Biểu mẫu, tự động điền, xuất DOCX | 32/32 |
| `test-signing.ps1` | Chữ ký, PIN, mã băm trước/sau | 33/33 |
| `test-approval.ps1` | Luồng trình ký hai cấp | 42/42 |
| `test-rbac-routes.ps1` | Phân quyền ở backend theo route | 26/26 |
| `test-security.ps1` | IDOR, upload giả đuôi, rate limit, path traversal | 27/27 |

Các bộ này kiểm bằng **request thật với tài khoản không có quyền**, không phải bằng cách xem giao
diện có ẩn nút hay không. Ví dụ tiêu biểu: `test-signing.ps1` sửa đúng **một byte** của file đã ký
rồi gọi endpoint kiểm chứng, để chứng minh mã băm thật sự phát hiện được.

## Sao lưu và khôi phục

```bash
pwsh scripts/sao-luu.ps1               # PostgreSQL + Qdrant + storage/ + chỉ mục BM25
pwsh scripts/khoi-phuc.ps1             # khôi phục bản mới nhất
```

`.env` **không** nằm trong bản sao lưu — nó chứa khóa API và mật khẩu, cần cất giữ riêng.

## Cấu trúc

```text
client/               React + Vite — giao diện ba nhóm người dùng
server/api/           NestJS — auth/RBAC, tài liệu, lịch, biểu mẫu, chữ ký, trình ký
server/rag-service/   FastAPI — pipeline RAG
server/data/          Corpus và dữ liệu nguồn thật của Học viện
server/storage/       Sinh lúc chạy: tệp tải lên, đơn đã dựng, ảnh chữ ký
copus/                Corpus đã chuẩn hóa cho RAG (quy chế, giáo trình, lịch học)
scripts/              Phân tích, chuẩn hóa corpus, sao lưu, khôi phục, bộ kiểm thử
```

## Những chỗ dễ vấp

**Cổng 5433.** PostgreSQL map ra 5433 ở phía host vì 5432 thường đã bị một PostgreSQL khác chiếm.
Bên trong Docker network vẫn là `postgres:5432`.

**Hạn mức mô hình ngôn ngữ.** Chỉ dùng Gemini. Khóa miễn phí chỉ đủ vài truy vấn mỗi ngày; khi cạn,
dịch vụ RAG mở ngắt mạch 15 phút và **vẫn chạy**: truy xuất, xếp hạng và cổng từ chối hoạt động
bình thường, chỉ mất phần sinh câu trả lời. Hạn mức Gemini tự phục hồi lúc nửa đêm.

**Gõ tiếng Việt không dấu.** Corpus có dấu đầy đủ, nên truy vấn không dấu sẽ trượt truy xuất và bị
cổng abstention từ chối. Đây là hạn chế đã biết, chưa xử lý trong MVP.

**Chỉ một biểu mẫu được làm trọn vẹn.** Đơn xin phép nghỉ học (01–03 ngày). Sáu biểu mẫu còn lại
được khai báo trong cơ sở dữ liệu nhưng `is_active = false`, và giao diện nói thẳng là chưa mở —
liệt kê để biết chúng tồn tại, không phải để bấm vào rồi gặp trang lỗi.
