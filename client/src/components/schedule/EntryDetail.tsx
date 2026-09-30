import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError } from '@/services/api';
import {
  dateOf,
  scheduleApi,
  timeOf,
  weekdayOf,
  type Exam,
  type ScheduleEntry,
  type Session,
} from '@/services/schedule-api';
import { Icon } from '@/components/shared/Icon';

const NOTE_MAX = 4000;

/** Định dạng thời gian cập nhật "HH:mm dd/MM/yyyy" theo giờ Việt Nam. */
function updatedAtOf(iso: string): string {
  const d = new Date(iso);
  const hm = new Intl.DateTimeFormat('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(d);
  return `${hm} ${dateOf(iso)}`;
}

interface Row {
  label: string;
  value: ReactNode;
}

/** Dòng "Thời gian" — buổi học có tiết, ca thi có số phút + ca. */
function timeRow(entry: ScheduleEntry): string {
  if (entry.kind === 'EXAM') {
    const e = entry as Exam;
    return `${weekdayOf(e.startsAt)}, ${dateOf(e.startsAt)} · ${timeOf(e.startsAt)} · ${e.durationMinutes} phút${
      e.shift ? ` · ca ${e.shift}` : ''
    }`;
  }
  const s = entry as Session;
  return `${weekdayOf(s.startsAt)}, ${dateOf(s.startsAt)} · ${timeOf(s.startsAt)}–${timeOf(s.endsAt)} · tiết ${s.startPeriod}–${s.endPeriod}`;
}

function buildRows(entry: ScheduleEntry): Row[] {
  const rows: Row[] = [];
  const push = (label: string, value: ReactNode) => {
    if (value === null || value === undefined || value === '') return;
    rows.push({ label, value });
  };

  push('Thời gian', timeRow(entry));
  push('Phòng', `${entry.room}${entry.building ? ` · ${entry.building}` : ''}`);

  if (entry.kind === 'SESSION') {
    const s = entry as Session;
    if (s.instructor) push('Giảng viên', s.instructor);
    if (s.lecturer && s.lecturer.name !== s.instructor) {
      push('Phụ trách môn', `${s.lecturer.name} (${s.lecturer.email})`);
    }
    push('Hình thức học', s.deliveryMode);
  } else {
    const e = entry as Exam;
    push('Hình thức thi', e.formatLabel);
    push('Được mang vào', e.allowedMaterials);
    push('Cán bộ coi thi', [e.chiefProctor, e.secondProctor].filter(Boolean).join(' · '));
    push('Số thí sinh', e.candidateCount !== null ? String(e.candidateCount) : null);
  }

  if (entry.class) push('Lớp', entry.class.code);
  return rows;
}

/**
 * Bảng chi tiết một buổi học / ca thi — drawer bên phải. Dùng `<dialog>` gốc
 * với `showModal()`: Esc đóng, focus tự bị giữ trong dialog, focus trả về khối
 * đã bấm (đang focus) khi đóng.
 */
export function EntryDetail({
  entry,
  onClose,
  editable = false,
  onSaved,
  onEdit,
  onDelete,
}: {
  entry: ScheduleEntry;
  onClose: () => void;
  editable?: boolean;
  onSaved?: (updated: ScheduleEntry) => void;
  /** Có nút "Sửa" cho buổi/ca thi (chỉ người có quyền tạo/sửa). */
  onEdit?: () => void;
  /** Có nút "Xóa" buổi/ca thi — kèm hộp thoại xác nhận trong trang. */
  onDelete?: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(entry.lecturerNote?.text ?? '');
  const [notify, setNotify] = useState(true);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [removing, setRemoving] = useState(false);

  // Nhãn cho hộp thoại xác nhận xóa: tên môn + ngày.
  const removeLabel =
    entry.kind === 'EXAM'
      ? `ca thi ${entry.course.code} — ${entry.course.name}, ngày ${dateOf((entry as Exam).startsAt)}`
      : `buổi học ${entry.course.code} — ${entry.course.name}, ngày ${dateOf((entry as Session).startsAt)}`;

  useEffect(() => {
    dialogRef.current?.showModal();
  }, []);

  const close = useCallback(() => {
    dialogRef.current?.close();
  }, []);

  // "Xóa yêu cầu" được gọi lại với cùng tham số khi bấm nhầm — đặt cờ xác nhận
  // thay vì gọi lại API; chỉ thực sự gọi API khi xác nhận.
  async function save(note: string | null) {
    setSaving(true);
    setError(null);
    try {
      const updated = await scheduleApi.setLecturerNote(entry, note, notify);
      onSaved?.(updated);
      setEditing(false);
      setConfirmDelete(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không lưu được yêu cầu. Thử lại.');
    } finally {
      setSaving(false);
    }
  }

  const isExam = entry.kind === 'EXAM';
  const cancelled = entry.status === 'CANCELLED' || entry.status === 'HOLIDAY';
  const session = !isExam ? (entry as Session) : null;
  const tag = isExam
    ? { label: 'Lịch thi', cls: 'tag--seal' }
    : cancelled
      ? { label: (entry as Session).statusLabel ?? 'đã hủy', cls: 'tag--warn' }
      : session
        ? { label: session.sessionTypeLabel, cls: 'tag--muted' }
        : null;
  const rows = buildRows(entry);
  const note = entry.lecturerNote;
  const remaining = NOTE_MAX - text.length;

  return (
    <dialog
      ref={dialogRef}
      className="entry-dlg"
      aria-labelledby="entry-detail-title"
      onClose={onClose}
    >
      <div className="entry-dlg__bar">
        <span className="eyebrow">Chi tiết buổi</span>
        <button type="button" className="btn btn--ghost btn--sm" onClick={close} aria-label="Đóng bảng chi tiết">
          <Icon name="close" size={16} />
          <span className="sr-only">Đóng</span>
        </button>
      </div>

      <div className="entry-dlg__body">
        <div className="entry-dlg__tags">
          {tag && <span className={`tag ${tag.cls}`}>{tag.label}</span>}
        </div>

        <h2 id="entry-detail-title" className="entry-dlg__title">
          {entry.course.code} — {entry.course.name}
        </h2>

        <dl className="entry-dl">
          {rows.map((r) => (
            <div key={r.label} className="entry-dl__row">
              <dt className="eyebrow">{r.label}</dt>
              <dd>{r.value}</dd>
            </div>
          ))}
        </dl>

        {/* ------------------------------------------------ yêu cầu của GV */}
        <section className="entry-note" aria-label="Yêu cầu của giảng viên">
          <h3 className="entry-note__head">Yêu cầu của giảng viên</h3>
          {note ? (
            <>
              <p className="entry-note__text">{note.text}</p>
              <p className="entry-note__meta">
                Cập nhật bởi {note.updatedBy ?? 'giảng viên'} · {updatedAtOf(note.updatedAt)}
              </p>
            </>
          ) : (
            <p className="entry-note__none">Giảng viên chưa ghi yêu cầu cho buổi này.</p>
          )}

          {editable && (
            <div className="entry-note__edit">
              {editing ? (
                <>
                  <textarea
                    className="field__input entry-note__input"
                    value={text}
                    maxLength={NOTE_MAX}
                    rows={6}
                    placeholder="Mang gì, đọc trước gì, chuẩn bị gì cho buổi này…"
                    onChange={(e) => setText(e.target.value)}
                  />
                  <div className="entry-note__count mono">
                    {remaining} ký tự còn lại
                  </div>
                  <label className="row entry-note__notify">
                    <input
                      type="checkbox"
                      checked={notify}
                      onChange={(e) => setNotify(e.target.checked)}
                    />
                    <span>Báo cho học viên của lớp</span>
                  </label>

                  {error && (
                    <p className="notice notice--error" role="alert">
                      {error}
                    </p>
                  )}

                  <div className="row entry-note__actions">
                    <button
                      type="button"
                      className="btn btn--primary btn--sm"
                      disabled={saving}
                      onClick={() => void save(text.trim() || null)}
                    >
                      {saving ? 'Đang lưu…' : 'Lưu'}
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      disabled={saving}
                      onClick={() => {
                        setEditing(false);
                        setConfirmDelete(false);
                        setError(null);
                        setText(note?.text ?? '');
                      }}
                    >
                      Hủy
                    </button>
                    {note && (
                      <button
                        type="button"
                        className="btn btn--quiet btn--sm"
                        disabled={saving}
                        onClick={() => setConfirmDelete(true)}
                      >
                        Xóa yêu cầu
                      </button>
                    )}
                  </div>

                  {confirmDelete && (
                    <p className="entry-note__confirm">
                      Xóa yêu cầu này?
                      <span className="row" style={{ marginTop: '0.4rem' }}>
                        <button
                          type="button"
                          className="btn btn--danger btn--sm"
                          disabled={saving}
                          onClick={() => void save(null)}
                        >
                          {saving ? 'Đang xóa…' : 'Xóa'}
                        </button>
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          disabled={saving}
                          onClick={() => setConfirmDelete(false)}
                        >
                          Giữ lại
                        </button>
                      </span>
                    </p>
                  )}
                </>
              ) : (
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() => {
                    setText(note?.text ?? '');
                    setNotify(true);
                    setError(null);
                    setConfirmDelete(false);
                    setEditing(true);
                  }}
                >
                  <Icon name="pencil" size={15} />
                  Sửa yêu cầu
                </button>
              )}
            </div>
          )}
        </section>

        {/* ------------------------------------------------ ghi chú phòng ĐT */}
        {entry.note && (
          <p className="entry-note__training">
            <span className="eyebrow" style={{ display: 'block', marginBottom: '0.25rem' }}>
              Ghi chú của phòng đào tạo
            </span>
            {entry.note}
          </p>
        )}

        {/* --------------------------------------------- sửa/xóa buổi (có quyền) */}
        {(onEdit || onDelete) && (
          <div className="sedit-entry-actions">
            {onEdit && (
              <button type="button" className="btn btn--ghost btn--sm" onClick={onEdit}>
                <Icon name="pencil" size={15} />
                Sửa
              </button>
            )}
            {onDelete && (
              <button
                type="button"
                className="btn btn--danger btn--sm"
                onClick={() => setConfirmRemove(true)}
                disabled={removing}
              >
                <Icon name="trash" size={15} />
                Xóa
              </button>
            )}
          </div>
        )}

        {confirmRemove && onDelete && (
          <div className="sedit-confirm" role="alertdialog" aria-labelledby="sedit-confirm-title">
            <p id="sedit-confirm-title" className="sedit-confirm__text">
              Xóa {removeLabel}? Hành động này không thể hoàn tác.
            </p>
            <div className="sedit-confirm__actions">
              <button
                type="button"
                className="btn btn--danger btn--sm"
                disabled={removing}
                onClick={async () => {
                  setRemoving(true);
                  try {
                    await onDelete();
                  } finally {
                    setRemoving(false);
                    setConfirmRemove(false);
                  }
                }}
              >
                {removing ? 'Đang xóa…' : 'Xóa'}
              </button>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => setConfirmRemove(false)}
                disabled={removing}
              >
                Giữ lại
              </button>
            </div>
          </div>
        )}
      </div>
    </dialog>
  );
}
