import { useEffect, useState } from 'react';
import { SignaturePad } from './SignaturePad';
import { signaturesApi, viDateTime, type SignatureInfo } from '@/services/forms-api';

/**
 * Quản lý chữ ký mẫu trên trang Hồ sơ cá nhân.
 *
 * Đăng ký chữ ký mới sẽ vô hiệu hóa chữ ký cũ nhưng không xóa nó: những đơn đã
 * ký bằng chữ ký cũ vẫn phải tra ngược lại được.
 */
export function SignatureCard() {
  const [sig, setSig] = useState<SignatureInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [drawing, setDrawing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Đổi sau mỗi lần lưu để trình duyệt nạp lại ảnh thay vì dùng bản cache. */
  const [version, setVersion] = useState(0);

  useEffect(() => {
    signaturesApi
      .mine()
      .then(setSig)
      .catch(() => setSig(null))
      .finally(() => setLoading(false));
  }, []);

  async function save(png: Blob) {
    setBusy(true);
    setError(null);
    try {
      setSig(await signaturesApi.register(png));
      setVersion((v) => v + 1);
      setDrawing(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="sheet sheet--pad">
      <span className="eyebrow">Chữ ký</span>
      <h2 className="display" style={{ fontSize: '1.15rem', margin: '0.35rem 0 0.5rem' }}>
        Chữ ký điện tử nội bộ
      </h2>
      <p style={{ color: 'var(--ink-soft)', fontSize: '0.875rem', maxWidth: 'var(--measure)', margin: '0 0 var(--gap-5)' }}>
        Nét chữ ký này được chèn vào đơn khi bạn xác nhận bằng mã PIN ký. Hệ thống lưu mã băm của
        file trước và sau khi ký, kèm thời điểm và địa chỉ truy cập — đủ để đối chiếu về sau, nhưng
        đây không phải chữ ký số công cộng theo quy định về chứng thư số.
      </p>

      {error && (
        <div className="notice notice--error" role="alert" style={{ marginBottom: 'var(--gap-4)' }}>
          {error}
        </div>
      )}

      {loading ? (
        <p className="eyebrow">Đang tải…</p>
      ) : drawing ? (
        <SignaturePad busy={busy} onSave={save} />
      ) : sig ? (
        <div>
          <div
            style={{
              border: '1px solid var(--rule-faint)',
              background: 'var(--paper)',
              padding: 'var(--gap-4)',
              maxWidth: '20rem',
            }}
          >
            <img
              src={`${signaturesApi.imageUrl()}?v=${version}`}
              alt="Chữ ký của bạn"
              style={{ display: 'block', width: '100%', height: 'auto' }}
            />
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', margin: 'var(--gap-3) 0 0' }}>
            Đăng ký {viDateTime(sig.createdAt)} · mã băm{' '}
            <span className="mono">{sig.fileHash.slice(0, 16)}…</span>
          </p>
          <div className="row" style={{ marginTop: 'var(--gap-4)' }}>
            <button type="button" className="btn btn--ghost" onClick={() => setDrawing(true)}>
              Vẽ chữ ký mới
            </button>
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', margin: 'var(--gap-3) 0 0', maxWidth: 'var(--measure)' }}>
            Chữ ký mới thay thế chữ ký này cho các đơn ký từ nay về sau. Đơn đã ký giữ nguyên nét cũ
            — nếu không thì mã băm của chúng sẽ không còn giải thích được.
          </p>
        </div>
      ) : (
        <div>
          <div className="notice notice--info" style={{ marginBottom: 'var(--gap-4)' }}>
            Bạn chưa có chữ ký. Chưa có chữ ký thì chưa ký được đơn nào.
          </div>
          <button type="button" className="btn btn--primary" onClick={() => setDrawing(true)}>
            Vẽ chữ ký
          </button>
        </div>
      )}
    </section>
  );
}
