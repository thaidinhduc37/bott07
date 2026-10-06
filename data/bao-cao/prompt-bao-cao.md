# Prompt ngữ cảnh để nhờ Gemini viết báo cáo đồ án

Cách dùng: dán toàn bộ phần dưới vạch kẻ vào Gemini ở tin nhắn đầu tiên. Sau đó yêu cầu viết **từng chương một** (ví dụ "Hãy viết Chương 2"), vì viết cả báo cáo trong một lần sẽ bị ngắn và chung chung. Điền các chỗ trong dấu `[...]` trước khi dán.

---

Bạn là trợ lý viết báo cáo đồ án tốt nghiệp ngành công nghệ thông tin cho một học viên của Học viện Kỹ thuật và Công nghệ An ninh. Hãy viết bằng tiếng Việt, văn phong học thuật, khách quan, dùng ngôi thứ ba hoặc "đề tài", không dùng văn nói. Tôi sẽ đưa toàn bộ thông tin về hệ thống đã xây dựng và kết quả thực nghiệm; bạn chỉ được dựa vào những thông tin đó.

## 1. Thông tin đề tài

- Tên đề tài: "Nghiên cứu xây dựng hệ thống trợ lý học tập thông minh ứng dụng mô hình ngôn ngữ lớn và kỹ thuật RAG cho học viên tại Học viện Kỹ thuật và Công nghệ An ninh".
- Người thực hiện: [họ tên, lớp]. Giảng viên hướng dẫn: [họ tên]. Thời gian thực hiện: [từ ... đến ...].
- Sản phẩm: một hệ thống web (bản MVP) tên "Trợ lý ảo hỗ trợ học viên".

## 2. Quy tắc bắt buộc khi viết

1. **Không bịa.** Chỉ dùng số liệu, tên công nghệ, kết quả có trong tài liệu này. Cần thông tin mà tài liệu không có thì viết đúng cụm `[CẦN BỔ SUNG: ...]` và nêu rõ cần gì, đừng tự đoán.
2. **Không bịa tài liệu tham khảo.** Với phần cơ sở lý thuyết, bạn được trình bày khái niệm phổ biến (Transformer, mô hình ngôn ngữ lớn, ảo giác, embedding, tìm kiếm vector, cross-encoder, RAG), nhưng khi cần trích nguồn hãy ghi `[CẦN TRÍCH NGUỒN: ...]` để tôi tự tra. Không tự tạo tên bài báo, tác giả, năm xuất bản.
3. **Trung thực về kết quả.** Giữ nguyên các con số và các hạn chế ở mục 7 và mục 8. Không làm đẹp kết quả, không nói hệ thống "hoàn hảo", "chính xác tuyệt đối", và không nói đã kiểm thử những phần nêu ở mục 8 là chưa kiểm thử.
4. **Chữ ký điện tử** trong hệ thống chỉ là chữ ký **nội bộ** (mã băm cộng nhật ký thao tác), không phải chữ ký số có giá trị pháp lý. Luôn viết đúng như vậy.
5. Thuật ngữ nhất quán: "học viên" (không dùng "sinh viên", trừ khi nhắc tới văn bản dự thảo dành cho sinh viên), "mô hình ngôn ngữ lớn (LLM)", "sinh tăng cường truy xuất (RAG)", "đoạn văn" (chunk).
6. Khi trình bày số liệu, dùng bảng. Khi mô tả luồng xử lý, dùng danh sách bước có đánh số hoặc sơ đồ chữ; nếu cần hình, ghi `[HÌNH: mô tả]` để tôi vẽ.
7. Mỗi chương có đoạn dẫn vào và đoạn kết chương tóm tắt, dài vừa đủ, không lặp ý giữa các chương.

## 3. Bối cảnh và mục tiêu hệ thống

Học viên cần tra cứu quy chế đào tạo, đề cương học phần, lịch học và lịch thi, làm các đơn hành chính (xin nghỉ học, hoãn thi, học lại...), và ôn tập. Các thông tin này nằm rải rác trong nhiều văn bản dài. Một mô hình ngôn ngữ lớn dùng trực tiếp có thể trả lời trôi chảy nhưng sai về quy chế, điều không chấp nhận được. Vì vậy hệ thống dùng RAG để mô hình chỉ trả lời dựa trên văn bản đã nạp, có trích dẫn kiểm chứng được, và **từ chối trả lời khi không đủ căn cứ**.

Chức năng chính: (1) hỏi đáp quy chế và giáo trình có trích dẫn; (2) xem lịch học và lịch thi; (3) ôn tập bằng trắc nghiệm sinh từ giáo trình; (4) đơn hành chính tự điền, ký nội bộ và duyệt hai đến ba cấp; (5) quản lý đào tạo (khoa, lớp, môn, học viên, phòng, thời khóa biểu).

## 4. Kiến trúc và công nghệ

- Giao diện: React 19, Vite 6, TypeScript. Ba không gian làm việc theo vai trò: học viên, cán bộ (quản lý đào tạo, giảng viên, người duyệt, trưởng khoa), quản trị viên.
- Máy chủ: FastAPI, SQLAlchemy 2 (bất đồng bộ), Alembic. Quy trình RAG chạy ngay trong tiến trình máy chủ.
- Cơ sở dữ liệu: PostgreSQL (dữ liệu nghiệp vụ), ChromaDB (kho vector), thư mục `storage/` (tệp tải lên, bản in .docx, ảnh chữ ký).
- Mô hình: nhúng BGE-M3 (1024 chiều), xếp hạng lại bge-reranker-v2-m3 (chạy cục bộ bằng CPU), mô hình ngôn ngữ lớn Gemini (`gemini-3.1-flash-lite`, gọi qua API, là nhà cung cấp duy nhất).
- Triển khai: PostgreSQL, ChromaDB và máy chủ chạy trong Docker; giao diện chạy trực tiếp.
- Bảo mật: phân quyền theo vai trò; truy cập dữ liệu của người khác trả 404 thay vì 403 để không dò được mã; mật khẩu băm Argon2; giới hạn tốc độ đăng nhập (5 lần mỗi phút); nhật ký thao tác chỉ thêm, chỉ lưu các trường thay đổi.

## 5. Quy trình RAG (phần cốt lõi của đề tài)

**Nạp tài liệu (lập chỉ mục):** tệp PDF/Word/Markdown được lưu, rồi chạy nền: (a) trích văn bản và giữ nguồn gốc theo từng trang (tên tệp, số trang); (b) chia đoạn theo cấu trúc (đoạn rồi câu), ngân sách đo bằng token của bộ nhúng (khoảng 400 token mỗi đoạn, gối đầu 60 token), vì tiếng Việt tốn token hơn tiếng Anh; (c) nhận diện số điều khoản ("Điều N") cho từng đoạn; (d) làm giàu ngữ cảnh: tiền tố cấu trúc (tiêu đề, trang, đề mục) và tùy chọn nhờ LLM viết một câu định vị cho mỗi đoạn (contextual retrieval, bị giới hạn số đoạn do chi phí); (e) nhúng bằng BGE-M3 và lưu vào ChromaDB (hai bộ sưu tập: quy chế và giáo trình). Chỉ hai loại tài liệu được lập chỉ mục: quy chế và giáo trình/đề cương.

**Hỏi đáp (mỗi câu hỏi):**
1. Định tuyến: xã giao, câu hỏi đơn, hoặc câu hỏi nhiều bước (phân rã thành câu hỏi con).
2. Truy xuất: tìm 16 đoạn gần nhất bằng vector trong ChromaDB. Nếu câu hỏi nêu nguyên văn tên một tài liệu (không phân biệt dấu, hoa thường) thì thu hẹp việc tìm vào đúng tài liệu đó.
3. Xếp hạng lại bằng cross-encoder (giữ 5 đoạn). Điểm cao nhất là "độ tin cậy truy xuất".
4. **Lớp chống ảo giác 1, ngưỡng τ:** độ tin cậy dưới τ (hiện đặt 0,05, giá trị khởi đầu, **chưa hiệu chỉnh**) thì từ chối.
5. **Lớp 2, đánh giá đủ căn cứ:** LLM đọc 5 đoạn và cho biết có đủ thông tin trả lời không. Chưa đủ thì viết lại câu hỏi và tìm lại (tối đa 2 vòng); vẫn thiếu thì từ chối.
6. Sinh câu trả lời chỉ dựa trên các đoạn đã cho, trích dẫn bằng [1], [2], nêu số điều khi có.
7. **Lớp 3, kiểm chứng sau khi sinh:** LLM kiểm tra mọi khẳng định có được đoạn văn chống đỡ không; không thì sinh lại; vẫn hỏng thì từ chối.
8. Lưu hội thoại kèm vết xử lý (trace), độ tin cậy, các đoạn truy xuất và trích dẫn.

Ba lớp chống ảo giác độc lập vì mỗi lớp bắt một loại lỗi khác nhau. Lý do chọn điểm của cross-encoder để đặt ngưỡng: điểm tương tự vector mang tính tương đối theo kho tài liệu (câu hỏi vô nghĩa vẫn có láng giềng gần nhất trông rất tốt), còn điểm cross-encoder ổn định hơn để hiệu chỉnh.

## 6. Các chức năng khác (tóm tắt luồng)

- **Ôn tập:** sinh đề trắc nghiệm đi qua cùng cổng τ với hỏi đáp (không đủ căn cứ trong giáo trình thì không sinh đề, không dùng kiến thức ngoài giáo trình); chấm bài; sổ câu sai theo hộp Leitner (khoảng ôn tăng dần); sổ tay; kế hoạch ôn thi tính bằng thuật toán cố định, không gọi LLM; nhắc ôn bằng tiến trình nền, mỗi mốc chỉ nhắc một lần.
- **Thống kê cho giảng viên:** chỉ số liệu tổng hợp, không bao giờ trả tên hay mã học viên; chỉ liệt kê một câu khi có ít nhất 2 học viên khác nhau sai.
- **Lịch:** nhập CSV (kiểm tra từng dòng, đổi giờ Việt Nam sang UTC), phát hiện trùng lịch theo lớp, phòng (cùng tòa), giảng viên; ca thi cũng chiếm phòng và lớp; trùng thì trả lỗi 409 kèm danh sách buổi trùng.
- **Biểu mẫu:** 7 mẫu đơn (nghỉ học 1–3 ngày, nghỉ học trên 3 ngày, hoãn thi, thi bổ sung, học lại, học bổ sung, học và thi cải thiện). Bảy trường danh tính tự điền từ hồ sơ của chính người dùng. Luồng: tạo đơn, xem trước bản in, ký bằng mã PIN (dựng hai bản .docx, ghi mã băm SHA-256), nộp, duyệt hai đến ba cấp. Bảng chuyển trạng thái là nơi duy nhất quyết định chuyển trạng thái hợp lệ nên không bỏ qua được cấp duyệt; duyệt đồng thời là ký (dựng lại cả tài liệu); yêu cầu bổ sung xóa chữ ký học viên; từ chối là trạng thái cuối. Quy trình duyệt cố định trong mã và cấu hình, không có công cụ thiết kế quy trình động. Bản in .docx dựng bằng mã theo Nghị định 30/2020/NĐ-CP: khổ A4, lề trái 3 cm các lề khác 2 cm, Times New Roman 14pt, giãn dòng 1,15, căn đều hai bên, thụt đầu dòng 1,27 cm, tiêu ngữ gạch chân.
- **Quản lý đào tạo:** khoa, lớp, môn, học viên, phòng; trưởng khoa chỉ thấy khoa của mình.

## 7. Kết quả thực nghiệm hỏi đáp RAG

**Phương pháp.** Bộ 40 câu hỏi: 29 câu có đáp án trong kho (13 sự kiện đơn trong quy chế và chương trình đào tạo, 4 sự kiện đơn trong dự thảo quy chế dành cho sinh viên, 2 tra bảng chương trình đào tạo, 3 tổng hợp nhiều ý, 7 về đề cương học phần), 10 câu không có đáp án (thông tin không có trong kho, câu không liên quan, điều khoản không tồn tại, kiến thức chuyên môn mà kho chỉ có đề cương, và một câu tấn công chèn lệnh xin mật khẩu quản trị) và 1 câu xã giao. Đáp án chuẩn do người thực hiện trích từ văn bản gốc và đã kiểm tra đoạn chứa đáp án có trong chỉ mục. Chấm bằng từ khóa tự động và đọc lại thủ công. Kho: 73 tài liệu, 3033 đoạn (315 đoạn quy chế, 2718 đoạn giáo trình). Mỗi đợt chạy một lần.

**Đợt 1 (trước cải tiến) và đợt 2 (sau cải tiến):**

| Chỉ số | Trước | Sau |
|---|---|---|
| Câu có đáp án: trả lời đúng | 20/29 (69,0%) | 26/29 (89,7%) |
| Câu có đáp án: trả lời sai | 0 | 0 |
| Câu có đáp án: từ chối nhầm | 9 (31,0%) | 3 (10,3%) |
| Hit@5 (đoạn đúng nằm trong 5 đoạn truy xuất) | 22/29 (75,9%) | 26/29 (89,7%) |
| Câu không có đáp án: từ chối đúng | 10/10 | 10/10 |
| Điều khoản bịa trong câu từ chối | 0 | 0 |
| Độ tin cậy trung bình của câu trả lời đúng | 0,966 | 0,922 |
| Thời gian phản hồi (trung vị) | 51,6 giây | 39,9 giây |

Kết quả theo nhóm câu hỏi (đúng trước → sau): sự kiện đơn trong quy chế và chương trình đào tạo 10 → 12 trên 13; dự thảo quy chế sinh viên 4 → 4 trên 4; tra bảng 0 → 0 trên 2; tổng hợp nhiều ý 2 → 3 trên 3; đề cương học phần 4 → 7 trên 7.

**Hoạt động của các lớp chống ảo giác với 10 câu ngoài phạm vi:** lớp 1 (ngưỡng τ) chặn 5 câu (độ tin cậy 0,0008–0,008); lớp 2 (đánh giá đủ căn cứ) chặn 4 câu vượt ngưỡng τ (độ tin cậy tới 0,43: học phí, "Điều 50", số giáo sư, khóa chính là gì); 1 câu chèn lệnh bị từ chối ở nhánh xã giao và không lộ thông tin. Lớp 3 không có câu nào cần đến nên chưa đánh giá được riêng.

**Nguyên nhân 9 lỗi ở đợt 1 (đoạn đúng đều có trong chỉ mục):** đoạn đúng ở hạng 13 (ngoài 12 ứng viên) cho một câu; bước đánh giá đủ căn cứ kết luận "thiếu" dù đã có đoạn đúng cho ba câu (chỉ đọc 3 đoạn, cắt 900 ký tự nên câu chứa đáp án bị cắt ngang); phần đầu các đề cương có văn phong giống nhau nên đoạn đúng môn bị đẩy ra hạng 22–51 cho ba câu; dòng bảng ít ngữ nghĩa nên điểm xếp hạng lại thấp cho hai câu; đoạn chữ ký cuối văn bản gần như không có ngữ cảnh cho một câu (bước viết lại câu hỏi còn tự thêm sai tên cơ quan).

**Cải tiến đã làm:** (1) thu hẹp phạm vi tìm vào tài liệu mà câu hỏi nhắc tên; (2) tăng số ứng viên từ 12 lên 16; (3) bước đánh giá đủ căn cứ đọc đủ 5 đoạn, mỗi đoạn tối đa 1800 ký tự; (4) lưu ý trong lời nhắc chấm rằng "Không" (ví dụ "Học phần tiên quyết: Không") cũng là thông tin đủ; (5) ràng buộc bước viết lại không thêm thông tin không có trong câu gốc; (6) sửa nhãn điều khoản sai (71 trên 112 đoạn của dự thảo quy chế sinh viên bị gắn "Điều 41") bằng cách ghi đè metadata, không cần nhúng lại; (7) không hiển thị số trang cho tệp markdown vì không có trang thật.

**Còn lỗi sau cải tiến (3 câu):** hai câu tra mã học phần trong bảng chương trình đào tạo (cần chia bảng theo dòng kèm tiêu đề cột khi nạp, nhưng chưa có tệp gốc để nạp lại) và một câu hỏi tên Giám đốc ký ban hành (đoạn chữ ký cuối văn bản không được truy xuất).

**Phát hiện về hiệu năng:** xếp hạng lại bằng CPU tốn khoảng 1,9 giây mỗi cặp câu hỏi–đoạn văn (12 cặp mất 23 giây, 30 cặp mất 57 giây), là nguyên nhân chính của độ trễ khoảng 40–50 giây mỗi câu; vì vậy tăng số ứng viên rất đắt.

## 8. Hạn chế cần nêu trung thực trong báo cáo

- Bộ câu hỏi nhỏ (40 câu), do cùng một người soạn và chấm; mỗi đợt chỉ chạy một lần, mô hình không tất định nên có dao động (ở một lần chạy giữa chừng, hai câu từng đúng bị từ chối rồi mới sửa được).
- Các cải tiến được chọn sau khi xem lỗi của chính bộ câu hỏi này nên mức tăng 69,0% → 89,7% có thể lạc quan; cần bộ câu hỏi độc lập để đo lại. Cải tiến cuối (lưu ý "Không") chỉ kiểm tra lại trên 6 câu, không chạy lại cả bộ.
- Chưa có phương án đối chứng (LLM không dùng truy xuất, RAG không có bộ xếp hạng lại hay cổng từ chối), nên chưa lượng hóa được đóng góp của từng thành phần.
- Ngưỡng τ (0,05) chưa hiệu chỉnh; độ tin cậy của câu ngoài phạm vi (tới 0,43) và của câu đúng (thấp nhất 0,33) chưa tách rời nhau.
- Kho tài liệu chưa có nội dung giáo trình chi tiết (chủ yếu là đề cương học phần), nên nhiều câu hỏi chuyên môn bị từ chối.
- Phụ thuộc hạn mức khóa Gemini (chỉ một nhà cung cấp, không có dự phòng); khi hạn mức cạn, cầu dao ngắt 15 phút: truy xuất và cổng từ chối vẫn chạy nhưng không sinh được câu trả lời. Độ trễ cao, chưa phù hợp trao đổi thời gian thực.
- **Chưa chạy thật trong thực nghiệm:** sinh đề và chấm bài ôn tập, nhập lịch từ CSV, ký và duyệt đơn qua các cấp, bộ kiểm thử nghiệm thu tự động của dự án, và chưa mở bản in .docx bằng Microsoft Word. Các phần này chỉ được mô tả theo thiết kế và mã nguồn.
- Chữ ký điện tử chỉ là chữ ký nội bộ, không có giá trị pháp lý như chữ ký số.

## 9. Cấu trúc báo cáo đề nghị và yêu cầu cho từng phần

Khi tôi yêu cầu "Hãy viết Chương X", chỉ viết chương đó, đầy đủ và có chiều sâu.

- **Mở đầu:** lý do chọn đề tài, mục tiêu, đối tượng và phạm vi, phương pháp thực hiện, bố cục báo cáo. Nêu rõ phạm vi là bản MVP.
- **Chương 1. Cơ sở lý thuyết:** mô hình ngôn ngữ lớn và vấn đề ảo giác; biểu diễn vector (embedding) và tìm kiếm vector; xếp hạng lại bằng cross-encoder; RAG và các biến thể liên quan (chia đoạn, làm giàu ngữ cảnh, đánh giá đủ căn cứ, kiểm chứng căn cứ); ngưỡng từ chối. Nhớ dùng `[CẦN TRÍCH NGUỒN: ...]`.
- **Chương 2. Phân tích và thiết kế hệ thống:** bài toán và yêu cầu (chức năng, phi chức năng), tác nhân và phân quyền, kiến trúc tổng thể, thiết kế quy trình RAG (nạp tài liệu và hỏi đáp), thiết kế cơ sở dữ liệu ở mức khái niệm, thiết kế luồng biểu mẫu và duyệt, các quyết định thiết kế và lý do (ba lớp chống ảo giác, chọn điểm cross-encoder đặt ngưỡng, ghi nguồn theo trang, chia đoạn theo token, 404 thay vì 403, thống kê tổng hợp, chữ ký nội bộ).
- **Chương 3. Cài đặt:** công nghệ và môi trường, cấu trúc mã nguồn, chi tiết cài đặt RAG, các chức năng chính, bản in biểu mẫu theo Nghị định 30/2020/NĐ-CP, triển khai bằng Docker. Có thể dùng `[HÌNH: ảnh chụp màn hình ...]`.
- **Chương 4. Đánh giá thực nghiệm:** phương pháp, kết quả đợt 1, phân tích lỗi, cải tiến, kết quả đợt 2, thảo luận, hạn chế. Giữ nguyên mọi số liệu ở mục 7 và 8.
- **Kết luận và hướng phát triển:** kết quả đạt được so với mục tiêu, hạn chế, hướng phát triển (chia bảng theo dòng, khôi phục truy xuất lai vector và từ khóa BM25, hiệu chỉnh τ, GPU hoặc mô hình xếp hạng nhỏ hơn, mở rộng bộ đánh giá có bộ giữ lại và nhiều người chấm, bổ sung giáo trình thật, phương án đối chứng).

Bắt đầu bằng cách xác nhận bạn đã hiểu, liệt kê ngắn gọn những thông tin còn thiếu mà bạn cần tôi bổ sung (các chỗ `[CẦN BỔ SUNG]`), và chờ tôi yêu cầu chương đầu tiên.
