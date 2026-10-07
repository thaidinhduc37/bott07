import { useState, type ReactNode } from 'react';
import { GradeImportReport } from '@/components/grades/GradeImport';
import { Icon } from '@/components/shared/Icon';
import { downloadText } from '@/utils/download';
import type { ImportResult } from '@/services/grades-staff-api';

/**
 * Khung nhập CSV dùng chung (học viên, ngân hàng câu hỏi…): chọn tệp → "Kiểm tra" (chạy thử, không ghi) →
 * chỉ cho nhập khi không còn dòng lỗi; cột phải có hướng dẫn định dạng, tệp mẫu và lưu ý.
 * `afterResult` chèn thêm nội dung sau khi nhập thật (vd nút tải mật khẩu của tài khoản mới).
 */
export function CsvImport<R extends ImportResult>({
  id,
  run,
  columns,
  exampleRow,
  sample,
  sampleName,
  notes,
  submitLabel,
  hint = 'Tệp UTF-8, dòng đầu là tên cột. Bấm “Kiểm tra” trước khi nhập.',
  afterResult,
  onAccepted,
}: {
  id: string;
  run: (file: File, dryRun: boolean) => Promise<R>;
  columns: string;
  exampleRow: string;
  sample: string;
  sampleName: string;
  notes: ReactNode[];
  submitLabel: string;
  hint?: string;
  afterResult?: (result: R) => ReactNode;
  /** Gọi sau khi nhập thật thành công (vd tải lại số câu của môn). */
  onAccepted?: (result: R) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<R | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function go(dryRun: boolean) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const r = await run(file, dryRun);
      setResult(r);
      if (r.accepted) onAccepted?.(r);
    } catch (e) {
      setError((e as Error).message || 'Nạp tệp thất bại');
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  const canImport = Boolean(file) && result !== null && result.dryRun && result.errors.length === 0;

  return (
    <div className="page-grid">
      <div className="page-grid__main">
        <form
          className="sheet sheet--pad"
          onSubmit={(e) => {
            e.preventDefault();
            void go(false);
          }}
        >
          <div className="field">
            <label className="field__label" htmlFor={id}>
              Tệp CSV<span className="req">*</span>
            </label>
            <input
              id={id}
              type="file"
              accept=".csv,text/csv"
              className="field__input"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setResult(null);
                setError(null);
              }}
              style={{ maxWidth: '36rem' }}
            />
            <span className="field__hint">{hint}</span>
          </div>

          <div className="row" style={{ marginTop: 'var(--gap-6)' }}>
            <button type="button" className="btn btn--ghost" onClick={() => void go(true)} disabled={busy || !file}>
              Kiểm tra
            </button>
            <button type="submit" className="btn btn--primary" disabled={busy || !canImport}>
              {busy ? 'Đang xử lý…' : submitLabel}
            </button>
          </div>
        </form>

        {error && (
          <div className="notice notice--error" role="alert">
            {error}
          </div>
        )}

        {result && afterResult?.(result)}
        {result && <GradeImportReport result={result} />}
      </div>

      <aside className="page-grid__aside">
        <section className="sheet sheet--pad">
          <h2 className="aside-h">Định dạng tệp</h2>
          <p className="field__hint" style={{ margin: '0 0 var(--gap-2)' }}>
            Dòng đầu là tên cột:
          </p>
          <code className="gent-cols">{columns}</code>
          <p className="field__hint" style={{ marginTop: 'var(--gap-3)' }}>
            Ví dụ một dòng:
          </p>
          <code className="gent-cols">{exampleRow}</code>
          <div style={{ marginTop: 'var(--gap-5)' }}>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => downloadText(sampleName, sample)}>
              <Icon name="form" size={16} />
              Tải tệp mẫu
            </button>
          </div>
        </section>

        <section className="sheet sheet--pad">
          <h2 className="aside-h">Lưu ý</h2>
          <ul className="gent-notes">
            {notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </section>
      </aside>
    </div>
  );
}
