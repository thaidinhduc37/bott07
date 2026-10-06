import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageHeader } from '@/components/shared/PageHeader';
import { useSession } from '@/components/shared/SessionProvider';
import { TabPanel, Tabs } from '@/components/shared/Tabs';
import { Icon } from '@/components/shared/Icon';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { ApiError } from '@/services/api';
import {
  gradesStaffApi,
  type GradeSection,
  type Roster,
  type RosterStudent,
  type ScoreInput,
} from '@/services/grades-staff-api';
import { GradeImport } from '@/components/grades/GradeImport';

const errText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

/** Các cột điểm thành phần + điểm học phần, kèm nhãn tiếng Việt. */
const SCORE_COLS = [
  { key: 'practice', label: 'TH' },
  { key: 'process', label: 'QT' },
  { key: 'midterm', label: 'GK' },
  { key: 'finalExam', label: 'CK' },
  { key: 'total', label: 'ĐHP' },
] as const;

type ScoreKey = (typeof SCORE_COLS)[number]['key'];

/** Trạng thái một ô điểm đang nhập (chuỗi thô từ input). */
interface Cell {
  raw: string;
  changed: boolean;
  invalid: boolean;
}

type Cells = Record<ScoreKey, Cell>;

type Part = 'class' | 'csv';

/**
 * Nhập điểm học phần. Giảng viên thường chỉ thấy phần "Nhập theo lớp";
 * cán bộ quản lý đào tạo / quản trị thêm tab "Nhập từ CSV".
 */
export default function GradeEntry() {
  useDocumentTitle('Nhập điểm');
  const { user } = useSession();
  const roles = user?.roles ?? [];
  const canImport = roles.includes('ACADEMIC_MANAGER') || roles.includes('ADMIN');
  const [part, setPart] = useState<Part>('class');

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Giảng dạy"
        title="Nhập điểm"
        description="Điểm học phần của các lớp bạn phụ trách."
        tabs={
          canImport ? (
            <Tabs
              label="Nội dung trang Nhập điểm"
              idPrefix="nhap-diem"
              value={part}
              onChange={setPart}
              items={[
                { id: 'class', label: 'Nhập theo lớp' },
                { id: 'csv', label: 'Nhập từ CSV' },
              ]}
            />
          ) : undefined
        }
      />

      {canImport ? (
        <TabPanel idPrefix="nhap-diem" tab={part}>
          {part === 'class' ? <ClassPart /> : <GradeImport />}
        </TabPanel>
      ) : (
        <ClassPart />
      )}
    </div>
  );
}

/* =====================================================================
   Nhập theo lớp: danh sách học phần bên trái + bảng nhập điểm bên phải. */

function ClassPart() {
  const [params, setParams] = useSearchParams();
  const [sections, setSections] = useState<GradeSection[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [termFilter, setTermFilter] = useState('');

  useEffect(() => {
    gradesStaffApi
      .sections()
      .then((r) => setSections(r.items))
      .catch((e) => setError(errText(e, 'Không tải được danh sách học phần')));
  }, []);

  // Các (năm học, học kỳ) khác nhau — chỉ hiện bộ lọc khi có nhiều hơn một.
  const terms = sections
    ? [...new Map(sections.map((s) => [`${s.academicYear}|${s.semester}`, `${s.academicYear}|${s.semester}`])).keys()]
    : [];
  const visible = termFilter ? sections?.filter((s) => `${s.academicYear}|${s.semester}` === termFilter) : sections;

  const selectedKey = params.get('mon');
  const selected = visible?.find((s) => `${s.course.id}|${s.class.id}|${s.academicYear}|${s.semester}` === selectedKey) ?? null;

  return (
    <div className="stack">
      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      {sections && sections.length === 0 ? (
        <div className="empty">
          <span className="empty__icon">
            <Icon name="book" size={22} />
          </span>
          <p className="empty__title">Chưa có học phần nào để nhập điểm</p>
          <p>Giảng viên chưa được phân công môn nào, hoặc các môn chưa có lịch học.</p>
        </div>
      ) : (
        <div className="page-grid page-grid--aside-left" style={{ ['--aside-w' as string]: '20rem' }}>
          <aside className="page-grid__aside">
            {terms.length > 1 && (
              <div className="field" style={{ marginBottom: 'var(--gap-4)' }}>
                <label className="field__label" htmlFor="gent-term">
                  Học kỳ
                </label>
                <select
                  id="gent-term"
                  className="field__input"
                  value={termFilter}
                  onChange={(e) => setTermFilter(e.target.value)}
                >
                  <option value="">Tất cả học kỳ</option>
                  {terms.map((t) => {
                    const [year, sem] = t.split('|');
                    return (
                      <option key={t} value={t}>
                        {sem} {year}
                      </option>
                    );
                  })}
                </select>
              </div>
            )}

            <div className="sheet" role="list" aria-label="Học phần">
              {(visible ?? []).map((s) => {
                const key = `${s.course.id}|${s.class.id}|${s.academicYear}|${s.semester}`;
                const on = key === selectedKey;
                return (
                  <button
                    key={key}
                    type="button"
                    role="listitem"
                    className={`gent-section${on ? ' gent-section--on' : ''}`}
                    aria-current={on ? 'true' : undefined}
                    onClick={() => setParams({ mon: key }, { replace: true })}
                  >
                    <span className="gent-section__name">
                      <span className="mono">{s.course.code}</span> — {s.course.name}
                    </span>
                    <span className="gent-section__meta">
                      Lớp {s.class.code} · {s.semester} {s.academicYear} · {s.gradedCount}/{s.studentCount} có điểm
                    </span>
                  </button>
                );
              })}
              {visible && visible.length === 0 && (
                <p className="eyebrow gent-section__loading">Không có học phần nào ở học kỳ này.</p>
              )}
              {!sections && <p className="eyebrow gent-section__loading">Đang tải…</p>}
            </div>
          </aside>

          <div className="page-grid__main">
            {selected ? (
              <RosterEditor
                key={`${selected.course.id}|${selected.class.id}|${selected.academicYear}|${selected.semester}`}
                section={selected}
                onLeave={() => {
                  const p = new URLSearchParams(params);
                  p.delete('mon');
                  setParams(p, { replace: true });
                }}
              />
            ) : (
              <div className="empty">
                <span className="empty__icon">
                  <Icon name="arrow" size={22} />
                </span>
                <p className="empty__title">Chọn một học phần</p>
                <p>Bấm vào một học phần ở danh sách bên trái để nhập điểm.</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* =====================================================================
   Bảng nhập điểm của một học phần. */

function RosterEditor({
  section,
  onLeave,
}: {
  section: GradeSection;
  onLeave: () => void;
}) {
  const [roster, setRoster] = useState<Roster | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cells, setCells] = useState<Record<string, Cells> | null>(null);
  const [noteCells, setNoteCells] = useState<Record<string, { raw: string; changed: boolean }> | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await gradesStaffApi.roster({
        courseId: section.course.id,
        classId: section.class.id,
        academicYear: section.academicYear,
        semester: section.semester,
      });
      setRoster(r);
      const c: Record<string, Cells> = {};
      const n: Record<string, { raw: string; changed: boolean }> = {};
      for (const st of r.students) {
        c[st.studentId] = {
          practice: { raw: fmt(st.practice), changed: false, invalid: false },
          process: { raw: fmt(st.process), changed: false, invalid: false },
          midterm: { raw: fmt(st.midterm), changed: false, invalid: false },
          finalExam: { raw: fmt(st.finalExam), changed: false, invalid: false },
          total: { raw: fmt(st.total), changed: false, invalid: false },
        };
        n[st.studentId] = { raw: st.note ?? '', changed: false };
      }
      setCells(c);
      setNoteCells(n);
    } catch (e) {
      setError(errText(e, 'Không tải được danh sách học viên'));
    } finally {
      setLoading(false);
    }
  }, [section]);

  useEffect(() => {
    void load();
  }, [load]);

  const students = roster?.students ?? [];
  const dirtyCount = countDirty(cells, noteCells, students);
  const hasInvalid = cells ? Object.values(cells).some((row) => Object.values(row).some((c) => c.invalid)) : false;

  // Chặn đóng / tải lại trình duyệt khi còn điểm chưa lưu.
  useEffect(() => {
    if (dirtyCount === 0) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [dirtyCount]);

  function setCell(studentId: string, key: ScoreKey, raw: string) {
    setCells((prev) => {
      if (!prev) return prev;
      const row = prev[studentId];
      return { ...prev, [studentId]: { ...row, [key]: { raw, changed: true, invalid: invalidScore(raw) } } };
    });
  }

  function setNote(studentId: string, raw: string) {
    setNoteCells((prev) => (prev ? { ...prev, [studentId]: { raw, changed: true } } : prev));
  }

  // Enter: nhảy xuống ô cùng cột của hàng dưới.
  function onEnter(e: KeyboardEvent<HTMLInputElement>, studentId: string, key: ScoreKey) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const idx = students.findIndex((s) => s.studentId === studentId);
    const next = students[idx + 1];
    if (next) {
      const input = document.getElementById(`gent-cell-${next.studentId}-${key}`) as HTMLInputElement | null;
      input?.focus();
    }
  }

  async function save() {
    if (!cells || !noteCells || hasInvalid) return;
    const items: ScoreInput[] = [];
    for (const st of students) {
      const row = cells[st.studentId];
      const note = noteCells[st.studentId];
      const changed = SCORE_COLS.some((col) => row[col.key].changed) || note.changed;
      if (!changed) continue;
      items.push({
        studentId: st.studentId,
        practice: toNum(row.practice.raw),
        process: toNum(row.process.raw),
        midterm: toNum(row.midterm.raw),
        finalExam: toNum(row.finalExam.raw),
        total: toNum(row.total.raw),
        note: note.raw.trim() || null,
      });
    }
    if (items.length === 0) return;
    setSaving(true);
    setSaveError(null);
    setSavedMsg(null);
    try {
      const r = await gradesStaffApi.saveScores({
        courseId: section.course.id,
        academicYear: section.academicYear,
        semester: section.semester,
        items,
      });
      setSavedMsg(`Đã lưu: tạo ${r.created}, cập nhật ${r.updated}`);
      window.setTimeout(() => setSavedMsg(null), 5000);
      await load();
    } catch (e) {
      setSaveError(errText(e, 'Không lưu được điểm. Thử lại.'));
    } finally {
      setSaving(false);
    }
  }

  function cancelLeave() {
    dialogRef.current?.close();
  }

  const invalidCount = hasInvalid ? countInvalid(cells) : 0;

  return (
    <div className="stack">
      <section className="sheet sheet--pad">
        <div className="section-head">
          <h2 className="aside-h">
            <span className="mono">{section.course.code}</span> — {section.course.name}
          </h2>
          <span className="section-head__note">
            Lớp {section.class.code} · {section.semester} {section.academicYear}
          </span>
        </div>

        <div className="notice notice--info" style={{ marginTop: 'var(--gap-4)' }}>
          Hệ thống không tự tính điểm học phần từ các điểm thành phần; hãy nhập điểm học phần theo quy chế của môn.
        </div>

        {loading ? (
          <p className="eyebrow" style={{ marginTop: 'var(--gap-6)' }}>
            Đang tải…
          </p>
        ) : error ? (
          <div className="notice notice--error" role="alert" style={{ marginTop: 'var(--gap-6)' }}>
            {error}
          </div>
        ) : students.length === 0 ? (
          <div className="empty" style={{ marginTop: 'var(--gap-6)' }}>
            <p className="empty__title">Chưa có học viên nào</p>
            <p>Lớp này chưa có học viên nào trong hệ thống.</p>
          </div>
        ) : (
          <>
            <div className="table-wrap" style={{ marginTop: 'var(--gap-6)' }}>
              <table className="data-table gent-table">
                <thead>
                  <tr>
                    <th scope="col">Mã HV</th>
                    <th scope="col">Họ tên</th>
                    {SCORE_COLS.map((c) => (
                      <th key={c.key} scope="col" style={{ textAlign: 'center' }}>
                        {c.label}
                      </th>
                    ))}
                    <th scope="col">Ghi chú</th>
                  </tr>
                </thead>
                <tbody>
                  {students.map((st) => {
                    const row = cells?.[st.studentId];
                    const note = noteCells?.[st.studentId];
                    return (
                      <tr key={st.studentId}>
                        <td className="mono">{st.studentCode}</td>
                        <td className="gent-name">{st.fullName}</td>
                        {SCORE_COLS.map((c) => (
                          <td key={c.key} style={{ textAlign: 'center' }}>
                            <input
                              id={`gent-cell-${st.studentId}-${c.key}`}
                              type="text"
                              inputMode="decimal"
                              className={`gent-cell${row?.[c.key].changed ? ' gent-cell--changed' : ''}${
                                row?.[c.key].invalid ? ' gent-cell--invalid' : ''
                              }`}
                              aria-label={`${labelOf(c.key)} của ${st.fullName}`}
                              aria-invalid={row?.[c.key].invalid || undefined}
                              value={row?.[c.key].raw ?? ''}
                              onChange={(e) => setCell(st.studentId, c.key, e.target.value)}
                              onKeyDown={(e) => onEnter(e, st.studentId, c.key)}
                            />
                          </td>
                        ))}
                        <td>
                          <input
                            type="text"
                            className="gent-note"
                            aria-label={`Ghi chú của ${st.fullName}`}
                            value={note?.raw ?? ''}
                            placeholder="—"
                            onChange={(e) => setNote(st.studentId, e.target.value)}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {hasInvalid && (
              <p className="field__error" role="alert" style={{ marginTop: 'var(--gap-3)' }}>
                {invalidCount} ô điểm không hợp lệ — phải là số từ 0 đến 10 (dùng dấu chấm hoặc dấu phẩy thập phân).
              </p>
            )}

            <div className="row gent-actions" style={{ marginTop: 'var(--gap-6)' }}>
              {dirtyCount > 0 && (
                <span className="tag tag--warn" role="status">
                  {dirtyCount} ô đã sửa
                </span>
              )}
              <span style={{ marginLeft: 'auto' }}>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={saving || dirtyCount === 0 || hasInvalid}
                  onClick={() => void save()}
                >
                  {saving ? 'Đang lưu…' : 'Lưu điểm'}
                </button>
              </span>
            </div>
          </>
        )}
      </section>

      {savedMsg && (
        <div className="notice notice--ok" role="status">
          {savedMsg}
        </div>
      )}
      {saveError && (
        <div className="notice notice--error" role="alert">
          {saveError}
        </div>
      )}

      <dialog
        ref={dialogRef}
        className="gent-dlg"
        aria-labelledby="gent-leave-title"
        onClose={cancelLeave}
      >
        <div className="gent-dlg__body">
          <h2 id="gent-leave-title" className="gent-dlg__title">
            Chưa lưu điểm
          </h2>
          <p className="gent-dlg__text">
            Bạn còn {dirtyCount} ô điểm chưa lưu. Rời đi mà không lưu sẽ mất các thay đổi này.
          </p>
          <div className="row gent-dlg__actions">
            <button type="button" className="btn btn--ghost" onClick={cancelLeave}>
              Tiếp tục nhập
            </button>
            <button type="button" className="btn btn--danger" onClick={onLeave}>
              Rời đi
            </button>
          </div>
        </div>
      </dialog>
    </div>
  );
}

/* ------------------------------------------------------------- tiện ích */

const fmt = (n: number | null) => (n === null ? '' : String(n));
const toNum = (raw: string): number | null => {
  const v = raw.trim().replace(',', '.');
  if (v === '') return null;
  return Number(v);
};
const invalidScore = (raw: string): boolean => {
  const v = raw.trim().replace(',', '.');
  if (v === '') return false;
  const n = Number(v);
  return Number.isNaN(n) || n < 0 || n > 10;
};
const labelOf = (key: ScoreKey): string => {
  const map: Record<ScoreKey, string> = {
    practice: 'Điểm TH',
    process: 'Điểm QT',
    midterm: 'Điểm GK',
    finalExam: 'Điểm CK',
    total: 'Điểm học phần',
  };
  return map[key];
};

function countDirty(
  cells: Record<string, Cells> | null,
  noteCells: Record<string, { raw: string; changed: boolean }> | null,
  students: RosterStudent[],
): number {
  if (!cells || !noteCells) return 0;
  let n = 0;
  for (const st of students) {
    const row = cells[st.studentId];
    if (row) for (const c of SCORE_COLS) if (row[c.key].changed) n += 1;
    if (noteCells[st.studentId]?.changed) n += 1;
  }
  return n;
}

function countInvalid(cells: Record<string, Cells> | null): number {
  if (!cells) return 0;
  let n = 0;
  for (const row of Object.values(cells)) for (const c of Object.values(row)) if (c.invalid) n += 1;
  return n;
}
