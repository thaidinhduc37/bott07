import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Field } from '@/components/shared/Field';
import { ApiError, authApi } from '@/services/api';
import { homePathOf } from '@/utils/roles';

export function LoginForm() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const nextPath = params.get('tiep-tuc');

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await authApi.login(email.trim(), password);
      // Đích đến đến từ query string, tức là từ người dùng — chỉ nhận đường dẫn
      // nội bộ. "//evil.com" là một đường dẫn hợp lệ với trình duyệt và sẽ đưa
      // người dùng ra ngoài nếu không chặn.
      const safeNext = nextPath && nextPath.startsWith('/') && !nextPath.startsWith('//') ? nextPath : null;
      navigate(safeNext ?? homePathOf(res.user.roles), { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(
          err.status === 429
            ? 'Bạn đã thử đăng nhập quá nhiều lần. Vui lòng đợi một phút rồi thử lại.'
            : err.message,
        );
      } else {
        setError('Không kết nối được tới máy chủ. Kiểm tra xem dịch vụ API đã chạy chưa.');
      }
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} style={{ marginTop: 'var(--gap-8)' }} noValidate>
      {error && (
        <div className="notice notice--error" role="alert" style={{ marginBottom: 'var(--gap-2)' }}>
          {error}
        </div>
      )}

      <Field
        label="Địa chỉ thư điện tử"
        type="email"
        name="email"
        autoComplete="username"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
        disabled={busy}
      />

      <Field
        label="Mật khẩu"
        type="password"
        name="password"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        disabled={busy}
      />

      <div style={{ marginTop: 'var(--gap-8)' }}>
        <button type="submit" className="btn btn--primary btn--lg btn--block" disabled={busy}>
          {busy ? 'Đang kiểm tra…' : 'Đăng nhập'}
        </button>
      </div>

      <p
        style={{
          marginTop: 'var(--gap-6)',
          paddingTop: 'var(--gap-4)',
          borderTop: '1px solid var(--rule-faint)',
          fontSize: '0.8125rem',
          color: 'var(--ink-faint)',
          marginBottom: 0,
        }}
      >
        Quên mật khẩu? Liên hệ Phòng Quản lý học viên để được cấp lại.
      </p>
    </form>
  );
}
