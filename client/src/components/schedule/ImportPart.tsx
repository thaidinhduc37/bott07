import { useEffect, useState } from 'react';
import { api } from '@/services/api';
import { scheduleApi, type ImportResult } from '@/services/schedule-api';

export interface ClassRef {
  id: string;
  code: string;
  name: string;
}

const SCHEDULE_COLS = [
  'schedule_id',
  'academic_year',
  'semester',
  'class_code',
  'course_code',
  'course_name',
  'credits',
  'session_date',
  'start_period',
  'end_period',
  'start_time',
  'end_time',
  'room',
  'session_type',
  'status',
];

const EXAM_COLS = [
  'exam_id',
  'academic_year',
  'semester',
  'class_code',
  'course_code',
  'course_name',
  'credits',
  'exam_date',
  'exam_shift',
  'start_time',
  'duration_minutes',
  'room',
  'exam_format',
  'status',
];

export function ImportPart() {
  const [classes, setClasses] = useState<ClassRef[]>([]);
  const [classId, setClassId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [allowPartial, setAllowPartial] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
            <label className="field__label" htmlFor="lop">
              Lớp<span className="req">*</span>
            </label>
            <select
              id="lop"
              className="field__input"
              value={classId}
              onChange={(e) => setClassId(e.target.value)}
              required
              style={{ maxWidth: '36rem' }}
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
              type="file"
              accept=".csv,text/csv"
              className="field__input"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setResult(null);
              }}
              required
              style={{ maxWidth: '36rem' }}
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
        </form>

        {error && (
          <div className="notice notice--error" role="alert">
            {error}
          </div>
        )}

        {result && <ImportReport result={result} />}
      </div>

      <aside className="page-grid__aside">
        <section className="sheet sheet--pad">
          <h2 className="aside-h">Định dạng tệp</h2>
          <p className="staff-sched-cols">
            Tệp có cột <code>schedule_id</code> được nhận là lịch học, cột{' '}
            <code>exam_id</code> là lịch thi. Cột bắt buộc:
          </p>
          <p className="field__hint" style={{ margin: '0 0 var(--gap-2)' }}>Lịch học</p>
          <code className="staff-sched-cols__code">{SCHEDULE_COLS.join(', ')}</code>
          <p className="field__hint" style={{ margin: 'var(--gap-4) 0 var(--gap-2)' }}>Lịch thi</p>
          <code className="staff-sched-cols__code">{EXAM_COLS.join(', ')}</code>
        </section>

        <section className="sheet sheet--pad">
          <h2 className="aside-h">Lưu ý</h2>
          <ul className="staff-sched-notes">
            <li>
              Hệ thống kiểm tra từng dòng, báo rõ dòng nào sai ở cột nào, và cảnh báo khi có buổi
              trùng lớp, trùng phòng hoặc trùng giảng viên.
            </li>
            <li>Dòng thuộc lớp khác bị báo lỗi, không bị lọc bỏ âm thầm.</li>
            <li>
              Tùy chọn “vẫn nạp các dòng hợp lệ” — mặc định là không, để tránh một thời khóa
              biểu thiếu buổi mà không ai biết.
            </li>
            <li>“Kiểm tra thử” chạy đủ mọi kiểm tra nhưng không ghi gì vào hệ thống.</li>
          </ul>
        </section>
      </aside>
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
                    <td className="mono" style={{ padding: '0.4rem 0.6rem 0.4rem 0', color: 'var(--ink-soft)' }}>
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
