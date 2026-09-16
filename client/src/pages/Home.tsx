import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '@/services/api';
import { homePathOf } from '@/utils/roles';

/**
 * Trang gốc chỉ làm một việc: hỏi backend xem người này là ai rồi đưa về đúng
 * khu vực.
 *
 * Middleware không làm được việc này vì nó không đọc được vai trò — nó chỉ thấy
 * cookie có tồn tại hay không, còn nội dung token thì cần secret để xác minh, và
 * secret không nên có mặt ở tầng edge.
 */
export default function RootPage() {
  const navigate = useNavigate();

  useEffect(() => {
    authApi
      .me()
      .then((me) => navigate(homePathOf(me.roles), { replace: true }))
      .catch(() => navigate('/dang-nhap', { replace: true }));
  }, [navigate]);

  return (
    <div style={{ display: 'grid', placeItems: 'center', minHeight: '100dvh' }}>
      <p className="eyebrow">Đang chuyển hướng…</p>
    </div>
  );
}
