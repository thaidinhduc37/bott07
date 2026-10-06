import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Field } from '@/components/shared/Field';
import { useSession } from '@/components/shared/SessionProvider';
import { SignatureCard } from '@/components/signature/SignatureCard';
import { ApiError, authApi } from '@/services/api';
import { viDate, viDateTime } from '@/services/forms-api';
import { PageHeader } from '@/components/shared/PageHeader';

/** Hàng dữ liệu chỉ đọc, trình bày như một dòng đã điền sẵn trên biểu mẫu. */
function ReadOnlyRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(9rem, 14rem) 1fr',
        gap: 'var(--gap-3)',
        padding: '0.55rem 0',
        borderBottom: '1px dotted var(--rule)',
        alignItems: 'baseline',
      }}
    >
      <span style={{ fontSize: '0.8125rem', color: 'var(--ink-soft)' }}>{label}</span>
      <span className={mono ? 'mono' : undefined} style={{ fontWeight: 500 }}>
        {value}
      </span>
    </div>
  );
}

export default function ProfilePage() {
  const { user, loading, reload } = useSession();

  const [phone, setPhone] = useState('');
  const [address, setAddress] = useState('');
  const [placeOfBirth, setPlaceOfBirth] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [fieldErrors, setFieldErrors] = useState<string[]>([]);

  useEffect(() => {
    if (!user) return;
    setPhone(user.phone ?? '');
    setAddress(user.studentProfile?.address ?? '');
    setPlaceOfBirth(user.studentProfile?.placeOfBirth ?? '');
  }, [user]);

  if (loading) return <p className="eyebrow">Đang tải hồ sơ…</p>;
  if (!user) return null;

  const profile = user.studentProfile;

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaveMsg(null);
    setFieldErrors([]);
    try {
      await authApi.updateProfile({
        phone: phone.trim() || undefined,
        ...(profile ? { address: address.trim(), placeOfBirth: placeOfBirth.trim() } : {}),
      });
      await reload();
      setSaveMsg({ kind: 'ok', text: 'Đã lưu thay đổi.' });
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors ?? []);
        setSaveMsg({ kind: 'error', text: err.message });
      } else {
        setSaveMsg({ kind: 'error', text: 'Không lưu được. Kiểm tra kết nối tới máy chủ.' });
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="stack">
      <PageHeader title="Hồ sơ cá nhân" description={user.roleNames.join(' · ')} />

      <div className="sheet sheet--pad">
        <section>
          <h2 className="eyebrow" style={{ marginBottom: 'var(--gap-2)' }}>
            Thông tin học vụ — do Phòng Quản lý học viên quản lý
          </h2>
          <p
            style={{
              fontSize: '0.8125rem',
              color: 'var(--ink-faint)',
              margin: '0 0 var(--gap-3)',
              maxWidth: 'var(--measure)',
            }}
          >
            Những trường này được điền tự động vào đơn bạn lập. Bạn không sửa được ở đây; nếu có sai
            sót, báo Phòng Quản lý học viên.
          </p>

          <ReadOnlyRow label="Họ và tên" value={user.fullName} />
          <ReadOnlyRow label="Thư điện tử" value={user.email} mono />
          {profile && (
            <>
              <ReadOnlyRow label="Mã số học viên" value={profile.studentCode} mono />
              <ReadOnlyRow label="Lớp" value={profile.studyClass?.code ?? '—'} />
              <ReadOnlyRow label="Khóa" value={profile.cohort ?? '—'} />
              <ReadOnlyRow label="Hệ đào tạo" value={profile.trainingSystem ?? '—'} />
              <ReadOnlyRow label="Ngày sinh" value={viDate(profile.dateOfBirth)} />
            </>
          )}
          <ReadOnlyRow label="Đăng nhập gần nhất" value={viDateTime(user.lastLoginAt)} />
        </section>

        <form onSubmit={onSave} style={{ marginTop: 'var(--gap-12)' }} noValidate>
          <h2 className="eyebrow" style={{ marginBottom: 'var(--gap-2)' }}>
            Thông tin liên hệ — bạn tự cập nhật
          </h2>

          {saveMsg && (
            <div
              className={`notice notice--${saveMsg.kind === 'ok' ? 'ok' : 'error'}`}
              role="alert"
              style={{ margin: 'var(--gap-3) 0' }}
            >
              {saveMsg.text}
              {fieldErrors.length > 1 && (
                <ul style={{ margin: '0.35rem 0 0', paddingLeft: '1.1rem' }}>
                  {fieldErrors.slice(1).map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <Field
            label="Số điện thoại"
            name="phone"
            inputMode="tel"
            hint="10 hoặc 11 chữ số, bắt đầu bằng 0"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            disabled={saving}
          />

          {profile && (
            <>
              <Field
                label="Nơi sinh"
                name="placeOfBirth"
                value={placeOfBirth}
                onChange={(e) => setPlaceOfBirth(e.target.value)}
                disabled={saving}
              />
              <Field
                label="Địa chỉ liên hệ"
                as="textarea"
                name="address"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                disabled={saving}
              />
            </>
          )}

          <div style={{ marginTop: 'var(--gap-6)' }}>
            <button type="submit" className="btn btn--primary" disabled={saving}>
              {saving ? 'Đang lưu…' : 'Lưu thay đổi'}
            </button>
          </div>
        </form>
      </div>

      <SignatureCard />

      <SecurityPanel hasPin={user.hasSignaturePin} />
    </div>
  );
}

// ---------------------------------------------------------------------------

function SecurityPanel({ hasPin }: { hasPin: boolean }) {
  const { reload } = useSession();
  const [searchParams] = useSearchParams();
  // Từ menu avatar, mục "Đổi mật khẩu" trỏ tới /ho-so?mode=password để mở
  // sẵn form này thay vì bắt người dùng bấm thêm một lần nữa trên trang.
  const [mode, setMode] = useState<'none' | 'password' | 'pin'>(
    searchParams.get('mode') === 'password' ? 'password' : 'none',
  );

  return (
    <div className="sheet sheet--pad">
      <span className="eyebrow">Bảo mật</span>
      <h2 className="display" style={{ fontSize: '1.2rem', margin: '0.35rem 0 var(--gap-4)' }}>
        Mật khẩu và mã PIN ký
      </h2>

      <p style={{ fontSize: '0.875rem', color: 'var(--ink-soft)', maxWidth: 'var(--measure)' }}>
        Mã PIN ký tách riêng khỏi mật khẩu đăng nhập. Ai đó chiếm được phiên của bạn vẫn không ký
        thay bạn được nếu không biết mã PIN.
      </p>

      <div className="row" style={{ marginTop: 'var(--gap-4)' }}>
        <span className={`tag ${hasPin ? 'tag--ok' : 'tag--warn'}`}>
          {hasPin ? 'Đã đặt mã PIN ký' : 'Chưa đặt mã PIN ký'}
        </span>
      </div>

      <div className="row" style={{ marginTop: 'var(--gap-4)' }}>
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() => setMode(mode === 'password' ? 'none' : 'password')}
        >
          Đổi mật khẩu
        </button>
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() => setMode(mode === 'pin' ? 'none' : 'pin')}
        >
          {hasPin ? 'Đổi mã PIN ký' : 'Đặt mã PIN ký'}
        </button>
      </div>

      {mode === 'password' && <ChangePasswordForm onDone={() => setMode('none')} />}
      {mode === 'pin' && (
        <SetPinForm
          onDone={async () => {
            setMode('none');
            await reload();
          }}
        />
      )}
    </div>
  );
}

function ChangePasswordForm({ onDone }: { onDone: () => void }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (next !== confirm) {
      setMsg('Hai lần nhập mật khẩu mới không khớp.');
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await authApi.changePassword(current, next);
      // Backend thu hồi mọi phiên sau khi đổi mật khẩu, nên phải đăng nhập lại.
      window.location.href = '/dang-nhap';
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : 'Không đổi được mật khẩu.');
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ marginTop: 'var(--gap-6)', maxWidth: '26rem' }} noValidate>
      {msg && (
        <div className="notice notice--error" role="alert">
          {msg}
        </div>
      )}
      <Field
        label="Mật khẩu hiện tại"
        type="password"
        autoComplete="current-password"
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
        required
        disabled={busy}
      />
      <Field
        label="Mật khẩu mới"
        type="password"
        autoComplete="new-password"
        hint="Ít nhất 8 ký tự, có cả chữ và số"
        value={next}
        onChange={(e) => setNext(e.target.value)}
        required
        disabled={busy}
      />
      <Field
        label="Nhập lại mật khẩu mới"
        type="password"
        autoComplete="new-password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        required
        disabled={busy}
      />
      <p style={{ fontSize: '0.8125rem', color: 'var(--ink-faint)', marginTop: 'var(--gap-3)' }}>
        Đổi mật khẩu sẽ đăng xuất bạn khỏi mọi thiết bị.
      </p>
      <div className="row" style={{ marginTop: 'var(--gap-4)' }}>
        <button type="submit" className="btn btn--primary" disabled={busy}>
          {busy ? 'Đang xử lý…' : 'Đổi mật khẩu'}
        </button>
        <button type="button" className="btn btn--quiet" onClick={onDone} disabled={busy}>
          Hủy
        </button>
      </div>
    </form>
  );
}

function SetPinForm({ onDone }: { onDone: () => void | Promise<void> }) {
  const [password, setPassword] = useState('');
  const [pin, setPin] = useState('');
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await authApi.setSignaturePin(password, pin);
      setMsg({ kind: 'ok', text: 'Đã cập nhật mã PIN ký.' });
      setPassword('');
      setPin('');
      await onDone();
    } catch (err) {
      setMsg({ kind: 'error', text: err instanceof ApiError ? err.message : 'Không đặt được mã PIN.' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ marginTop: 'var(--gap-6)', maxWidth: '26rem' }} noValidate>
      {msg && (
        <div className={`notice notice--${msg.kind === 'ok' ? 'ok' : 'error'}`} role="alert">
          {msg.text}
        </div>
      )}
      <Field
        label="Mật khẩu đăng nhập"
        type="password"
        autoComplete="current-password"
        hint="Xác nhận đúng là bạn trước khi đổi mã PIN"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        disabled={busy}
      />
      <Field
        label="Mã PIN ký"
        type="password"
        inputMode="numeric"
        maxLength={6}
        hint="Đúng 6 chữ số"
        value={pin}
        onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
        required
        disabled={busy}
      />
      <div className="row" style={{ marginTop: 'var(--gap-4)' }}>
        <button type="submit" className="btn btn--primary" disabled={busy || pin.length !== 6}>
          {busy ? 'Đang xử lý…' : 'Lưu mã PIN'}
        </button>
        <button type="button" className="btn btn--quiet" onClick={() => void onDone()} disabled={busy}>
          Hủy
        </button>
      </div>
    </form>
  );
}
