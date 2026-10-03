import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { LoginForm } from './LoginForm';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { authApi } from '@/services/api';
import { homePathOf } from '@/utils/roles';

/**
 * Cửa vào.
 *
 * Trước đây trang này mở đầu bằng masthead văn bản hành chính — quốc hiệu, tiêu
 * ngữ, gạch ngắn — rồi tới tiêu đề serif viết hoa. Ba khối chiếm gần nửa chiều
 * cao thẻ trước khi người dùng thấy ô nhập đầu tiên.
 *
 * Masthead thuộc về **tờ đơn**, và tờ đơn thật được dựng ở
 * `server/api/src/forms/docx-renderer.service.ts`, nơi nó in ra giấy và mang đúng
 * nghĩa. Đặt thêm một bản trên màn hình đăng nhập không làm hệ thống chính
 * thống hơn; nó chỉ đẩy việc người dùng tới đây để làm xuống dưới màn hình.
 *
 * Thay bằng phần đầu nói đúng ba điều cần thiết: đây là hệ thống gì, của ai, và
 * làm được gì.
 */
export default function LoginPage() {
  useDocumentTitle('Đăng nhập');
  const navigate = useNavigate();

  // Đã có phiên hợp lệ (cookie httpOnly) mà vào trang đăng nhập thì đưa về
  // trang chủ. Không đoán được bằng cách đọc cookie ở client — httpOnly cố
  // tình chặn JS đọc nó — nên phải hỏi thẳng backend.
  useEffect(() => {
    let cancelled = false;
    authApi
      .me()
      .then((me) => {
        if (!cancelled) navigate(homePathOf(me.roles), { replace: true });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  return (
    <main id="noi-dung" className="login">
      <div className="sheet sheet--pad login__card">
        <div className="login__head">
          <img className="rail__sigil" src="/logo.png" alt="" />
          <div>
            <h1 className="login__title">Trợ lý ảo hỗ trợ học viên</h1>
            <p className="login__org">Học viện Kỹ thuật và Công nghệ An ninh</p>
          </div>
        </div>

        {/* Mỗi năng lực là một `<span>` riêng — xem `.login__what` trong
            globals.css: đó là cách duy nhất buộc dòng chỉ ngắt ở giữa hai mục. */}
        <p className="login__what">
          <span>Hỏi đáp quy chế có trích dẫn</span>{' '}
          <span>Lịch học – lịch thi</span>{' '}
          <span>Biểu mẫu và trình ký</span>
        </p>

        <LoginForm />
      </div>
    </main>
  );
}
