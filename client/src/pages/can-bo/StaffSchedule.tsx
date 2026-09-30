import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/services/api';
import {
  dateOf,
  isoDate,
  mondayOf,
  scheduleApi,
  type CourseWithLecturer,
  type Exam,
  type ImportResult,
  type ScheduleEntry,
  type Session,
  type TeachingTimetable,
} from '@/services/schedule-api';
import { useSession } from '@/components/shared/SessionProvider';
import { TimetableWeek } from '@/components/schedule/TimetableWeek';
import { EntryDetail } from '@/components/schedule/EntryDetail';
import { SessionForm } from '@/components/schedule/SessionForm';
import { ExamForm } from '@/components/schedule/ExamForm';
import { Icon } from '@/components/shared/Icon';
import { PageHeader } from '@/components/shared/PageHeader';
import { TabPanel, Tabs } from '@/components/shared/Tabs';

interface ClassRef {
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

type Part = 'teaching' | 'import';

export default function StaffSchedulePage() {
  const { user } = useSession();
  const roles = user?.roles ?? [];
  // Phần "Nạp lịch từ CSV" chỉ dành cho cán bộ quản lý đào tạo / quản trị.
  const canImport = roles.includes('ACADEMIC_MANAGER') || roles.includes('ADMIN');
  const [part, setPart] = useState<Part>('teaching');

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Học vụ"
        title="Lịch học và lịch thi"
        description={
          canImport
            ? 'Lịch giảng dạy và nạp lịch từ tệp CSV.'
            : 'Buổi dạy, ca thi và yêu cầu của bạn cho từng buổi.'
        }
        tabs={
          canImport ? (
            <Tabs
              label="Nội dung trang Lịch"
              idPrefix="lich"
              value={part}
              onChange={setPart}
              items={[
                { id: 'teaching', label: 'Lịch giảng dạy' },
                { id: 'import', label: 'Nạp lịch từ CSV' },
              ]}
            />
          ) : undefined
        }
      />

      {canImport ? (
        <TabPanel idPrefix="lich" tab={part}>
          {part === 'teaching' ? <TeachingPart /> : <ImportPart />}
        </TabPanel>
      ) : (
        <TeachingPart />
      )}
    </div>
  );
}

/* =====================================================================
   Lịch giảng dạy: tuần trước / tuần này / tuần sau + lưới, bấm khối mở
   chi tiết để ghi yêu cầu của giảng viên. */

function TeachingPart() {
  const { user } = useSession();
  const roles = user?.roles ?? [];
  const isLecturer = roles.includes('LECTURER');
  // Cán bộ quản lý đào tạo / quản trị được tạo-sửa-xóa buổi và ca thi.
  const canManage = roles.includes('ACADEMIC_MANAGER') || roles.includes('ADMIN');
  const [weekStart, setWeekStart] = useState<Date>(() => mondayOf(new Date()));
  const [data, setData] = useState<TeachingTimetable | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ScheduleEntry | null>(null);
  // Lọc theo lớp — chỉ có ý nghĩa với cán bộ quản lý/quản trị (thấy mọi lớp).
  // Giảng viên đã chỉ thấy môn của mình nên không hiện bộ lọc.
  const [classes, setClasses] = useState<ClassRef[]>([]);
  const [classId, setClassId] = useState('');
  // Danh sách môn kèm giảng viên phụ trách — cho form tạo/sửa.
  const [courses, setCourses] = useState<CourseWithLecturer[]>([]);
  // Hộp thoại tạo/sửa: { kind: 'SESSION'|'EXAM', entry?: ScheduleEntry }.
  const [form, setForm] = useState<{ kind: 'SESSION' | 'EXAM'; entry: ScheduleEntry | null } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // Nút đã mở hộp thoại — để trả focus về khi đóng.
  const addSessionRef = useRef<HTMLButtonElement>(null);
  const addExamRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (isLecturer && !canManage) return;
    void api<{ items: ClassRef[] }>('/classes')
      .then((r) => setClasses(r.items))
      .catch(() => setClasses([]));
  }, [isLecturer, canManage]);

  useEffect(() => {
    if (!canManage) return;
    void scheduleApi
      .courses()
      .then((r) => setCourses(r.items))
      .catch(() => setCourses([]));
  }, [canManage]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const end = new Date(weekStart);
    end.setDate(weekStart.getDate() + 6);
    try {
      setData(
        await scheduleApi.teaching({ from: isoDate(weekStart), to: isoDate(end), classId: classId || undefined }),
      );
    } catch (e) {
      setData(null);
      setError(
        e instanceof Error ? e.message : 'Không tải được lịch giảng dạy. Kiểm tra kết nối tới máy chủ.',
      );
    } finally {
      setLoading(false);
    }
  }, [weekStart, classId]);

  useEffect(() => {
    void load();
  }, [load]);

  function shiftWeek(deltaWeeks: number) {
    const next = new Date(weekStart);
    next.setDate(weekStart.getDate() + deltaWeeks * 7);
    setWeekStart(next);
  }
  const isCurrentWeek = isoDate(weekStart) === isoDate(mondayOf(new Date()));

  // Sau khi lưu/xóa: tải lại tuần đang xem (giữ tuần + lớp), hiện thông báo ngắn.
  function flashNotice(msg: string) {
    setNotice(msg);
    window.setTimeout(() => setNotice(null), 4000);
  }

  function handleSaved(saved: ScheduleEntry) {
    setForm(null);
    setSelected(null);
    void load();
    flashNotice(saved.kind === 'EXAM' ? 'Đã lưu ca thi.' : 'Đã lưu buổi học.');
    addSessionRef.current?.focus();
  }

  async function handleDelete(entry: ScheduleEntry) {
    try {
      if (entry.kind === 'EXAM') await scheduleApi.deleteExam(entry.id);
      else await scheduleApi.deleteSession(entry.id);
      setSelected(null);
      void load();
      flashNotice(entry.kind === 'EXAM' ? 'Đã xóa ca thi.' : 'Đã xóa buổi học.');
      addSessionRef.current?.focus();
    } catch (e) {
      flashNotice(e instanceof Error ? e.message : 'Không xóa được. Thử lại.');
    }
  }

  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekStart.getDate() + 6);

  const sessions = data?.sessions ?? [];
  const exams = data?.exams ?? [];
  const all = [...sessions, ...exams];
  const empty = !loading && !error && all.length === 0;
  const noNoteCount = all.filter((e) => !e.lecturerNote).length;
  const firstNoNote = all.find((e) => !e.lecturerNote) ?? null;

  return (
    <div className="page-grid">
      <div className="page-grid__main">
        {/* ------------------------------------------- điều hướng tuần */}
        <div className="sheet" style={{ padding: '0.6rem 0.75rem' }}>
          <div className="row" style={{ gap: 'var(--gap-3)', flexWrap: 'wrap' }}>
            <div className="seg">
              <button type="button" className="seg__opt" onClick={() => shiftWeek(-1)}>
                Tuần trước
              </button>
              <button
                type="button"
                className={`seg__opt${isCurrentWeek ? ' seg__opt--on' : ''}`}
                onClick={() => setWeekStart(mondayOf(new Date()))}
              >
                Tuần này
              </button>
              <button type="button" className="seg__opt" onClick={() => shiftWeek(1)}>
                Tuần sau
              </button>
            </div>
            <span className="row" style={{ gap: '0.4rem', fontSize: '0.9375rem', color: 'var(--ink-soft)' }}>
              <Icon name="calendar" size={18} />
              <span className="mono">
                {dateOf(weekStart.toISOString())} – {dateOf(weekEnd.toISOString())}
              </span>
            </span>
            {data?.canEditAll && classes.length > 1 && (
              <label className="row teach-class-filter" style={{ gap: 'var(--gap-2)' }}>
                <span className="field__label" style={{ margin: 0 }}>Lớp</span>
                <select className="field__input" value={classId} onChange={(e) => setClassId(e.target.value)}>
                  <option value="">Tất cả lớp</option>
                  {classes.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.code}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {canManage && (
              <span className="row" style={{ gap: 'var(--gap-2)', marginLeft: 'auto' }}>
                <button
                  ref={addSessionRef}
                  type="button"
                  className="btn btn--primary"
                  onClick={() => setForm({ kind: 'SESSION', entry: null })}
                >
                  <Icon name="plus" size={16} />
                  Thêm buổi học
                </button>
                <button
                  ref={addExamRef}
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setForm({ kind: 'EXAM', entry: null })}
                >
                  <Icon name="plus" size={16} />
                  Thêm ca thi
                </button>
              </span>
            )}
          </div>
        </div>

        {notice && (
          <div className="notice notice--ok" role="status">
            {notice}
          </div>
        )}

        {error && (
          <div className="notice notice--error" role="alert">
            {error}
          </div>
        )}

        {loading ? (
          <p className="eyebrow">Đang tải…</p>
        ) : empty ? (
          <div className="empty">
            <span className="empty__icon">
              <Icon name="calendar" size={22} />
            </span>
            <p className="empty__title">Không có buổi dạy hay ca thi nào trong tuần này.</p>
            {isLecturer && (
              <p>Tài khoản chưa được gán môn nào — liên hệ phòng đào tạo.</p>
            )}
          </div>
        ) : (
          data && (
            <>
              <TimetableWeek
                sessions={sessions}
                exams={exams}
                from={data.range.from}
                to={data.range.to}
                onSelect={(e) => setSelected(e)}
                selectedKey={selected ? `${selected.kind}-${selected.id}` : undefined}
              />
              <p style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', margin: 0 }}>
                Giờ hiển thị theo múi giờ Việt Nam ({data.range.timezone}).
                {' '}
                {sessions.length} buổi dạy
                {exams.length > 0 && `, ${exams.length} ca thi`}
                {' '}trong tuần.
              </p>
            </>
          )
        )}
      </div>

      <aside className="page-grid__aside">
        <section className="sheet sheet--pad">
          <h2 className="aside-h">Tuần này</h2>
          <dl className="teach-stats">
            <div className="teach-stats__row">
              <dt>Buổi dạy</dt>
              <dd>{sessions.length}</dd>
            </div>
            <div className="teach-stats__row">
              <dt>Ca thi</dt>
              <dd>{exams.length}</dd>
            </div>
            <div className="teach-stats__row">
              <dt>Chưa có yêu cầu</dt>
              <dd>
                {noNoteCount > 0 && firstNoNote ? (
                  <button
                    type="button"
                    className="btn--quiet"
                    style={{ fontSize: 'inherit' }}
                    onClick={() => setSelected(firstNoNote)}
                  >
                    {noNoteCount}
                  </button>
                ) : (
                  noNoteCount
                )}
              </dd>
            </div>
          </dl>
        </section>

        <section className="sheet sheet--pad">
          <h2 className="aside-h">Hướng dẫn</h2>
          <ul className="staff-sched-notes">
            <li>
              Bấm vào buổi học hay ca thi để ghi yêu cầu: mang gì, đọc trước gì, chuẩn bị gì.
            </li>
            <li>Học viên của lớp nhận thông báo khi bạn lưu.</li>
            <li>
              Bỏ chọn “Báo cho học viên” khi chỉ sửa chính tả — không cần báo lại.
            </li>
          </ul>
        </section>
      </aside>

      {selected && (
        <EntryDetail
          entry={selected}
          onClose={() => setSelected(null)}
          editable
          onSaved={(updated) => {
            // Chỉ cập nhật mục trong state, không tải lại cả tuần.
            // Gộp vào mục cũ thay vì thay thế: API lưu ghi chú không trả `class`
            // (chỉ lịch giảng dạy mới có), thay nguyên mục sẽ làm mất mã lớp.
            setData((prev) => {
              if (!prev) return prev;
              if (updated.kind === 'EXAM') {
                return {
                  ...prev,
                  exams: prev.exams.map((x) => (x.id === updated.id ? { ...x, ...updated } : x)),
                };
              }
              return {
                ...prev,
                sessions: prev.sessions.map((s) => (s.id === updated.id ? { ...s, ...updated } : s)),
              };
            });
            setSelected((cur) => (cur ? ({ ...cur, ...updated } as ScheduleEntry) : cur));
          }}
          onEdit={
            canManage
              ? () => setForm({ kind: selected.kind, entry: selected })
              : undefined
          }
          onDelete={canManage ? () => void handleDelete(selected) : undefined}
        />
      )}

      {form && (
        <ScheduleFormDialog
          kind={form.kind}
          session={form.kind === 'SESSION' ? (form.entry as Session | null) : null}
          exam={form.kind === 'EXAM' ? (form.entry as Exam | null) : null}
          classes={classes}
          courses={courses}
          onSaved={handleSaved}
          onCancel={() => setForm(null)}
        />
      )}
    </div>
  );
}

/* =====================================================================
   Hộp thoại tạo/sửa buổi học hoặc ca thi — bọc SessionForm / ExamForm
   trong <dialog> (mẫu EntryDetail). */

function ScheduleFormDialog({
  kind,
  session,
  exam,
  classes,
  courses,
  onSaved,
  onCancel,
}: {
  kind: 'SESSION' | 'EXAM';
  session: Session | null;
  exam: Exam | null;
  classes: ClassRef[];
  courses: CourseWithLecturer[];
  onSaved: (e: ScheduleEntry) => void;
  onCancel: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const title =
    kind === 'SESSION'
      ? session
        ? 'Sửa buổi học'
        : 'Thêm buổi học'
      : exam
        ? 'Sửa ca thi'
        : 'Thêm ca thi';

  useEffect(() => {
    dialogRef.current?.showModal();
  }, []);

  return (
    <dialog ref={dialogRef} className="sedit-dlg" aria-labelledby="sedit-dialog-title" onClose={onCancel}>
      <div className="sedit-dlg__bar">
        <h2 id="sedit-dialog-title" className="sedit-dlg__title">
          {title}
        </h2>
        <button type="button" className="btn btn--ghost btn--sm" onClick={onCancel} aria-label="Đóng hộp thoại">
          <Icon name="close" size={16} />
          <span className="sr-only">Đóng</span>
        </button>
      </div>
      <div className="sedit-dlg__body">
        {kind === 'SESSION' ? (
          <SessionForm
            classes={classes}
            courses={courses}
            session={session}
            onSaved={onSaved}
            onCancel={onCancel}
          />
        ) : (
          <ExamForm classes={classes} courses={courses} exam={exam} onSaved={onSaved} onCancel={onCancel} />
        )}
      </div>
    </dialog>
  );
}

/* =====================================================================
   Nạp lịch từ CSV — giữ nguyên logic hiện có, chỉ bọc vào nhánh phần. */

function ImportPart() {
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
