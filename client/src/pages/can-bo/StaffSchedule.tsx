import { useEffect, useRef, useState } from 'react';
import { api } from '@/services/api';
import { scheduleApi, type ImportResult } from '@/services/schedule-api';

interface ClassRef {
  id: string;
  code: string;
  name: string;
}

export default function StaffSchedulePage() {
  const [classes, setClasses] = useState<ClassRef[]>([]);
  const [classId, setClassId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [allowPartial, setAllowPartial] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void api<{ items: ClassRef[] }>('/classes')
      .then((r) => {
        setClasses(r.items);
        if (r.items.length === 1) setClassId(r.items[0].id);
      })
      .catch(() => setClasses([]));
  }, []);

  async function run(dryRun: boolean) {
    if (!file || !classId) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await scheduleApi.import(file, classId, { dryRun, allowPartial }));
    } catch (e) {
      const err = e as { message?: string; body?: { message?: string } };
      setError(err.body?.message ?? err.message ?? 'Nạp tệp thất bại');
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <header>
        <span className="eyebrow">Học vụ</span>
        <h1 className="display page-title">
          Nạp lịch học và lịch thi
        </h1>
        <p className="page-sub">
          Tệp CSV xuất từ phần mềm xếp thời khóa biểu. Hệ thống kiểm tra từng dòng, báo rõ dòng
          nào sai ở cột nào, và cảnh báo khi có buổi trùng lớp, trùng phòng hoặc trùng giảng viên.
        </p>
      </header>

      <form
        className="sheet sheet--pad"
        onSubmit={(e) => {
          e.preventDefault();
          void run(false);
        }}
      >
        <div className="field">
          <label className="field__label" htmlFor="lop">
            Lớp<span className="req">*</span>
          </label>
          <select
            id="lop"
            className="field__input"
            value={classId}
            onChange={(e) => setClassId(e.target.value)}
            required
            style={{ maxWidth: '28rem' }}
          >
            <option value="">— chọn lớp —</option>
            {classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} — {c.name}
              </option>
            ))}
          </select>
          <span className="field__hint">
            Dòng nào trong tệp thuộc lớp khác sẽ bị báo lỗi, không bị lọc bỏ âm thầm.
          </span>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="tep">
            Tệp CSV<span className="req">*</span>
          </label>
          <input
            id="tep"
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            className="field__input"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setResult(null);
            }}
            required
          />
          <span className="field__hint">
            Nhận cả lịch học (cột <code>schedule_id</code>) và lịch thi (cột <code>exam_id</code>) —
            hệ thống tự nhận dạng.
          </span>
        </div>

        <label className="row" style={{ gap: '0.5rem', marginTop: 'var(--gap-4)', alignItems: 'flex-start' }}>
          <input
            type="checkbox"
            checked={allowPartial}
            onChange={(e) => setAllowPartial(e.target.checked)}
            style={{ marginTop: '0.25rem' }}
          />
          <span style={{ fontSize: '0.875rem' }}>
            Vẫn nạp các dòng hợp lệ dù tệp có dòng hỏng
            <span style={{ display: 'block', fontSize: '0.75rem', color: 'var(--ink-faint)' }}>
              Mặc định là không. Một thời khóa biểu thiếu buổi mà không ai biết là thiếu thì khó
              phát hiện hơn là một lần nạp bị từ chối.
            </span>
          </span>
        </label>

        <div className="row" style={{ marginTop: 'var(--gap-6)' }}>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => void run(true)}
            disabled={busy || !file || !classId}
          >
            Kiểm tra thử
          </button>
          <button type="submit" className="btn btn--primary" disabled={busy || !file || !classId}>
            {busy ? 'Đang xử lý…' : 'Nạp vào hệ thống'}
          </button>
        </div>
        <p style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', margin: 'var(--gap-3) 0 0' }}>
          “Kiểm tra thử” chạy đủ mọi kiểm tra nhưng không ghi gì vào hệ thống.
        </p>
      </form>

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      {result && <ImportReport result={result} />}
    </div>
  );
}

function ImportReport({ result }: { result: ImportResult }) {
  const ok = result.accepted && result.errors.length === 0;

  return (
    <section className="sheet sheet--pad">
      <div className="spread" style={{ marginBottom: 'var(--gap-4)' }}>
        <h2 className="display" style={{ fontSize: '1.15rem', margin: 0 }}>
          {result.dryRun ? 'Kết quả kiểm tra thử' : 'Kết quả nạp'}
        </h2>
        <span className={`tag ${ok ? 'tag--ok' : result.accepted ? 'tag--warn' : 'tag--seal'}`}>
          {ok ? 'sạch' : result.accepted ? 'có cảnh báo' : 'bị từ chối'}
        </span>
      </div>

      <div className={`notice notice--${ok ? 'ok' : result.accepted ? 'warn' : 'error'}`}>
        {result.message}
      </div>

      <dl
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(8rem, 1fr))',
          gap: 'var(--gap-4)',
          margin: 'var(--gap-6) 0 0',
        }}
      >
        {[
          ['Tệp', result.fileName],
          ['Lớp', result.class],
          ['Tổng số dòng', String(result.totalRows)],
          ['Dòng hợp lệ', String(result.validRows)],
          ['Đã nạp', String(result.imported)],
          ...(result.created !== undefined ? [['Tạo mới', String(result.created)] as const] : []),
          ...(result.updated !== undefined ? [['Cập nhật', String(result.updated)] as const] : []),
        ].map(([k, v]) => (
          <div key={k}>
            <dt className="eyebrow">{k}</dt>
            <dd className="mono" style={{ margin: '0.15rem 0 0', fontSize: '0.9375rem' }}>
              {v}
            </dd>
          </div>
        ))}
      </dl>

      {result.newCourses && result.newCourses.length > 0 && (
        <p style={{ marginTop: 'var(--gap-4)', fontSize: '0.875rem', color: 'var(--ink-soft)' }}>
          Đã tạo mới môn học: <span className="mono">{result.newCourses.join(', ')}</span>
        </p>
      )}

      {/* ------------------------------------------------------ lỗi theo dòng */}
      {result.errors.length > 0 && (
        <section style={{ marginTop: 'var(--gap-8)' }}>
          <h3 className="eyebrow" style={{ marginBottom: 'var(--gap-2)' }}>
            {result.errors.length} lỗi — sửa trong tệp rồi nạp lại
          </h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
              <thead>
                <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--rule)' }}>
                  <th style={{ padding: '0.4rem 0.6rem 0.4rem 0', width: '5rem' }}>Dòng</th>
                  <th style={{ padding: '0.4rem 0.6rem', width: '10rem' }}>Cột</th>
                  <th style={{ padding: '0.4rem 0' }}>Vấn đề</th>
                </tr>
              </thead>
              <tbody>
                {result.errors.slice(0, 60).map((e, i) => (
                  <tr key={i} style={{ borderBottom: '1px dotted var(--rule)' }}>
                    <td className="mono" style={{ padding: '0.4rem 0.6rem 0.4rem 0', color: 'var(--seal)' }}>
                      {e.line}
                    </td>
                    <td className="mono" style={{ padding: '0.4rem 0.6rem', color: 'var(--ink-soft)' }}>
                      {e.column ?? '—'}
                    </td>
                    <td style={{ padding: '0.4rem 0' }}>{e.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result.errors.length > 60 && (
            <p style={{ fontSize: '0.75rem', color: 'var(--ink-faint)' }}>
              …và {result.errors.length - 60} lỗi nữa.
            </p>
          )}
        </section>
      )}

      {/* -------------------------------------------------------- trùng lịch */}
      {result.conflicts.length > 0 && (
        <section style={{ marginTop: 'var(--gap-8)' }}>
          <h3 className="eyebrow" style={{ marginBottom: 'var(--gap-2)' }}>
            {result.conflicts.length} cảnh báo trùng lịch
          </h3>
          <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
            {result.conflicts.slice(0, 30).map((c, i) => (
              <li
                key={i}
                style={{
                  borderTop: '1px dotted var(--rule)',
                  padding: '0.45rem 0',
                  fontSize: '0.8125rem',
                }}
              >
                <span className="tag tag--warn" style={{ marginRight: '0.5rem' }}>
                  {c.kind === 'CLASS' ? 'lớp' : c.kind === 'ROOM' ? 'phòng' : 'giảng viên'}
                </span>
                {c.message}
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}
