import { useState } from 'react';
import { Icon } from '@/components/shared/Icon';
import { gradesStaffApi, type ImportResult } from '@/services/grades-staff-api';

const COLUMNS = 'ma_hv,ma_mon,nam_hoc,hoc_ky,th,qt,gk,ck,diem_hp,ghi_chu';

/** Hai dòng mẫu: tiêu đề + một dòng ví dụ. Dùng cho cả nút "Tải tệp mẫu". */
const SAMPLE = `${COLUMNS}\nHV20240001,SEC101,2026-2027,HK1,8,8,7,8,8,Đạt yêu cầu\n`;

function downloadSample() {
  const blob = new Blob([SAMPLE], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'mau-nhap-diem.csv';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/**
 * Nạp điểm từ tệp CSV — chỉ cán bộ quản lý đào tạo / quản trị.
 * "Kiểm tra" chạy `dryRun` (không ghi), sau đó mới cho "Nhập điểm" thật.
 */
export function GradeImport() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(dryRun: boolean) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await gradesStaffApi.import(file, dryRun));
    } catch (e) {
      const err = e as { message?: string; body?: { message?: string } };
      setError(err.body?.message ?? err.message ?? 'Nạp tệp thất bại');
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  const canImport = Boolean(file) && (result === null || (result.dryRun && result.errors.length === 0));

  return (
    <div className="page-grid">
      <div className="page-grid__main">
        <form
          className="sheet sheet--pad"
          onSubmit={(e) => {
            e.preventDefault();
            void run(false);
          }}
        >
          <div className="field">
            <label className="field__label" htmlFor="gent-file">
              Tệp CSV<span className="req">*</span>
            </label>
            <input
              id="gent-file"
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
            <span className="field__hint">Tệp UTF-8, dòng đầu là tên cột.</span>
          </div>

          <div className="row" style={{ marginTop: 'var(--gap-6)' }}>
            <button type="button" className="btn btn--ghost" onClick={() => void run(true)} disabled={busy || !file}>
              Kiểm tra
            </button>
            <button type="submit" className="btn btn--primary" disabled={busy || !canImport}>
              {busy ? 'Đang xử lý…' : 'Nhập điểm'}
            </button>
          </div>
        </form>

        {error && (
          <div className="notice notice--error" role="alert">
            {error}
          </div>
        )}

        {result && <GradeImportReport result={result} />}
      </div>

      <aside className="page-grid__aside">
        <section className="sheet sheet--pad">
          <h2 className="aside-h">Định dạng tệp</h2>
          <p className="field__hint" style={{ margin: '0 0 var(--gap-2)' }}>
            Dòng đầu là tên cột:
          </p>
          <code className="gent-cols">{COLUMNS}</code>
          <p className="field__hint" style={{ marginTop: 'var(--gap-3)' }}>
            Hai cột cuối (<code>diem_hp</code>, <code>ghi_chu</code>) tùy chọn. Ví dụ một dòng:
          </p>
          <code className="gent-cols">{SAMPLE.trim().split('\n')[1]}</code>
          <div style={{ marginTop: 'var(--gap-5)' }}>
            <button type="button" className="btn btn--ghost btn--sm" onClick={downloadSample}>
              <Icon name="form" size={16} />
              Tải tệp mẫu
            </button>
          </div>
        </section>

        <section className="sheet sheet--pad">
          <h2 className="aside-h">Lưu ý</h2>
          <ul className="gent-notes">
            <li>“Kiểm tra” chạy đủ mọi kiểm tra nhưng không ghi gì vào hệ thống.</li>
            <li>Chỉ cho nhập khi tệp không còn dòng lỗi.</li>
            <li>Một tệp tối đa 5.000 dòng.</li>
          </ul>
        </section>
      </aside>
    </div>
  );
}

function GradeImportReport({ result }: { result: ImportResult }) {
  const ok = result.accepted && result.errors.length === 0;

  return (
    <section className="sheet sheet--pad">
      <div className="spread" style={{ marginBottom: 'var(--gap-4)' }}>
        <h2 className="display" style={{ fontSize: '1.15rem', margin: 0 }}>
          {result.dryRun ? 'Kết quả kiểm tra' : 'Kết quả nhập'}
        </h2>
        <span className={`tag ${ok ? 'tag--ok' : result.accepted ? 'tag--warn' : 'tag--seal'}`}>
          {ok ? 'sạch' : result.accepted ? 'có cập nhật' : 'chưa ghi'}
        </span>
      </div>

      <div className={`notice notice--${ok ? 'ok' : result.accepted ? 'warn' : 'error'}`}>{result.message}</div>

      <dl
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(7rem, 1fr))',
          gap: 'var(--gap-4)',
          margin: 'var(--gap-6) 0 0',
        }}
      >
        {[
          ['Tổng số dòng', String(result.totalRows)],
          ['Dòng hợp lệ', String(result.validRows)],
          ['Tạo mới', String(result.created)],
          ['Cập nhật', String(result.updated)],
          ['Không đổi', String(result.unchanged)],
        ].map(([k, v]) => (
          <div key={k}>
            <dt className="eyebrow">{k}</dt>
            <dd className="mono" style={{ margin: '0.15rem 0 0', fontSize: '0.9375rem' }}>
              {v}
            </dd>
          </div>
        ))}
      </dl>

      {result.errors.length > 0 && (
        <section style={{ marginTop: 'var(--gap-8)' }}>
          <h3 className="eyebrow" style={{ marginBottom: 'var(--gap-2)' }}>
            {result.errors.length} dòng lỗi — sửa trong tệp rồi nhập lại
          </h3>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col" style={{ width: '5rem' }}>
                    Dòng
                  </th>
                  <th scope="col">Vấn đề</th>
                </tr>
              </thead>
              <tbody>
                {result.errors.slice(0, 60).map((e, i) => (
                  <tr key={i}>
                    <td className="mono" style={{ color: 'var(--seal)' }}>
                      {e.line}
                    </td>
                    <td>{e.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result.errors.length > 60 && (
            <p className="field__hint" style={{ marginTop: 'var(--gap-2)' }}>
              … và {result.errors.length - 60} dòng lỗi nữa.
            </p>
          )}
        </section>
      )}
    </section>
  );
}
