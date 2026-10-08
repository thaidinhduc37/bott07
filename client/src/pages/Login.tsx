import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { LoginForm } from './LoginForm';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { authApi } from '@/services/api';
import { homePathOf } from '@/utils/roles';

/**
  * Cửa vào. Không đặt masthead quốc hiệu ở đây: nó thuộc về tờ đơn (`server/app/services/forms/docx_renderer.py`) và chiếm
  * gần nửa chiều cao thẻ đăng nhập. Phần đầu chỉ nói ba điều: đây là hệ thống gì, của ai, làm được gì.
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
            styles/: đó là cách duy nhất buộc dòng chỉ ngắt ở giữa hai mục. */}
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
