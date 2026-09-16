import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Field } from '@/components/shared/Field';

export interface SignPanelProps {
  code: string;
  busy?: boolean;
  error?: string | null;
  /** Người dùng chưa đăng ký chữ ký thì không có gì để chèn vào đơn. */
  hasSignature: boolean;
  /** Điều khiển từ ngoài — nút bấm "Ký đơn" nằm ở header khung "Bản in" (góc
   * trên bên phải), không phải trong chính panel này nữa. */
  open: boolean;
  onClose: () => void;
  onSign: (pin: string) => void;
}

/**
 * Ký gồm hai bước bắt buộc theo đúng thứ tự: (1) xem đúng ô chữ ký sẽ được
 * chèn vào — cuộn bản xem trước tới ô đã tô sáng (`.doc-preview__sign-zone`,
 * xem `DocumentPreview.tsx`) và bắt xác nhận, (2) mới tới form nhập mã PIN.
 * Không cho nhảy thẳng vào bước 2: học viên phải THẤY vị trí trước khi ký,
 * không phải ký xong mới biết chữ ký nằm ở đâu.
 */
export function SignPanel({ code, busy, error, hasSignature, open, onClose, onSign }: SignPanelProps) {
  const [step, setStep] = useState<'confirm' | 'pin'>('confirm');
  const [pin, setPin] = useState('');

  useEffect(() => {
    if (!open) return;
    setStep('confirm');
    // Đợi DOM của bước "confirm" dựng xong rồi mới cuộn — cuộn ngay trong
    // cùng lượt render sẽ chạy trước khi trình duyệt tính lại layout.
    const t = window.setTimeout(() => {
      document.querySelector('.doc-preview__sign-zone')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 50);
    return () => window.clearTimeout(t);
  }, [open]);

  if (!hasSignature) {
    return (
      <div className="notice notice--warn" style={{ marginBottom: 'var(--gap-4)' }}>
        Bạn chưa đăng ký chữ ký nên chưa ký được đơn này.{' '}
        <Link to="/ho-so">Vẽ chữ ký ở trang Hồ sơ cá nhân</Link> rồi quay lại.
      </div>
    );
  }

  if (!open) return null;

  return (
    <div style={{ marginBottom: 'var(--gap-4)', paddingBottom: 'var(--gap-4)', borderBottom: '1px solid var(--rule-faint)' }}>
      <h3 style={{ margin: '0 0 var(--gap-3)', fontSize: '0.9375rem', fontWeight: 600 }}>Ký đơn {code}</h3>

      {step === 'confirm' ? (
        <>
          <p style={{ margin: '0 0 var(--gap-4)', fontSize: '0.875rem', color: 'var(--ink-soft)' }}>
            Chữ ký của bạn sẽ được chèn vào ô{' '}
            <strong style={{ color: 'var(--ink)' }}>“HỌC VIÊN VIẾT ĐƠN”</strong> — vừa được tô sáng
            trong bản xem trước bên cạnh. Xem đúng vị trí rồi mới tiếp tục nhập mã PIN; sau khi ký
            bạn không sửa được nội dung đơn nữa.
          </p>
          <div className="row">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setStep('pin')}
            >
              Đúng vị trí, tiếp tục
            </button>
            <button type="button" className="btn btn--ghost" onClick={onClose}>
              Hủy
            </button>
          </div>
        </>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSign(pin);
          }}
        >
          <Field
            label="Mã PIN ký"
            type="password"
            inputMode="numeric"
            autoComplete="off"
            required
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            hint="Mã PIN tách riêng khỏi mật khẩu đăng nhập. Đổi được ở trang Hồ sơ cá nhân."
            error={error ?? undefined}
          />
          <div className="row" style={{ marginTop: 'var(--gap-4)' }}>
            <button type="submit" className="btn btn--primary" disabled={busy || pin.length < 4}>
              {busy ? 'Đang ký…' : 'Xác nhận ký'}
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={busy}
              onClick={() => setStep('confirm')}
            >
              ← Xem lại vị trí
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={busy}
              onClick={() => {
                setPin('');
                onClose();
              }}
            >
              Hủy
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
