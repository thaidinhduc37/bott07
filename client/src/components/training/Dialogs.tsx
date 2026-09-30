import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react';
import { Icon } from '@/components/shared/Icon';
import { ApiError } from '@/services/api';
import {
  catalogApi,
  type ClassItem,
  type CourseItem,
  type LecturerItem,
} from '@/services/catalog-api';
import { facultyApi, type FacultyItem } from '@/services/faculty-api';

/**
 * Hộp thoại dùng chung cho trang Quản lý đào tạo.
 *
 * Dùng `<dialog>` gốc với `showModal()`: Esc đóng, focus tự bị giữ trong dialog
 * và trả về nút đã mở khi đóng (giống `EntryDetail`). Nút mở được truyền qua
 * `openRef` để focus trả về đúng chỗ.
 */

/** Khung hộp thoại căn giữa: tiêu đề + nút đóng + thân. */
export function TrainingDialog({
  openRef,
  title,
  titleId,
  onClose,
  children,
  forwardRef,
}: {
  openRef: React.RefObject<HTMLElement | null>;
  title: string;
  titleId: string;
  onClose: () => void;
  children: ReactNode;
  /** Ref để form bên trong tự đóng dialog khi bấm "Hủy". */
  forwardRef?: React.RefObject<HTMLDialogElement | null>;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = dialogRef.current;
    if (d && !d.open) d.showModal();
    // Trả focus về nút mở khi đóng (bấm backdrop, Esc, hay nút đóng).
    const onClosed = () => openRef.current?.focus();
    d?.addEventListener('close', onClosed);
    return () => d?.removeEventListener('close', onClosed);
  }, [openRef]);

  const close = useCallback(() => dialogRef.current?.close(), []);

  return (
    <dialog
      ref={(el) => {
        dialogRef.current = el;
        if (forwardRef) forwardRef.current = el;
      }}
      className="train-dlg"
      aria-labelledby={titleId}
      onClose={onClose}
    >
      <div className="train-dlg__bar">
        <h2 id={titleId} className="train-dlg__title">
          {title}
        </h2>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          onClick={close}
          aria-label="Đóng hộp thoại"
        >
          <Icon name="close" size={16} />
          <span className="sr-only">Đóng</span>
        </button>
      </div>
      <div className="train-dlg__body">{children}</div>
    </dialog>
  );
}

/**
 * Form thêm / sửa lớp. Khi `initial` có giá trị là chế độ sửa: mã khóa lại,
 * title đổi thành "Sửa lớp". Lỗi 409 (mã trùng) hiện nguyên `message` của API.
 */
export function ClassDialog({
  initial,
  openRef,
  onClose,
  onSaved,
}: {
  initial: ClassItem | null;
  openRef: React.RefObject<HTMLElement | null>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [code, setCode] = useState(initial?.code ?? '');
  const [name, setName] = useState(initial?.name ?? '');
  const [facultyId, setFacultyId] = useState(initial?.facultyId ?? '');
  const [cohortYear, setCohortYear] = useState(
    initial?.cohortYear != null ? String(initial.cohortYear) : '',
  );
  const [faculties, setFaculties] = useState<FacultyItem[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  const editing = initial != null;

  useEffect(() => {
    facultyApi
      .list()
      .then((r) => setFaculties(r.items))
      .catch(() => setFaculties([]));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (saving) return;
    setSaving(true);
    setError(null);
    const payload = {
      code: code.trim(),
      name: name.trim(),
      facultyId: facultyId || null,
      cohortYear: cohortYear.trim() ? Number(cohortYear) : null,
    };
    try {
      if (editing && initial) {
        // Chế độ sửa: mã không đổi, chỉ gửi các trường cho phép sửa.
        await catalogApi.updateClass(initial.id, {
          name: payload.name,
          facultyId: payload.facultyId,
          cohortYear: payload.cohortYear,
        });
      } else {
        await catalogApi.createClass(payload);
      }
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không lưu được lớp.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <TrainingDialog
      openRef={openRef}
      title={editing ? 'Sửa lớp' : 'Thêm lớp'}
      titleId="train-class-title"
      onClose={onClose}
      forwardRef={dialogRef}
    >
      <form onSubmit={(e) => void submit(e)}>
        <div className="field">
          <label className="field__label" htmlFor="train-class-code">
            Mã lớp<span className="req">*</span>
          </label>
          <input
            id="train-class-code"
            className="field__input"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            disabled={editing}
            required
            placeholder="VD: K25-AN-01"
          />
          {editing && (
            <span className="field__hint">Mã lớp không thể đổi sau khi đã tạo.</span>
          )}
        </div>

        <div className="field">
          <label className="field__label" htmlFor="train-class-name">
            Tên lớp<span className="req">*</span>
          </label>
          <input
            id="train-class-name"
            className="field__input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="VD: Lớp An ninh mạng 1"
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="train-class-faculty">
            Khoa
          </label>
          <select
            id="train-class-faculty"
            className="field__input"
            value={facultyId}
            onChange={(e) => setFacultyId(e.target.value)}
          >
            <option value="">— Chưa xếp khoa —</option>
            {faculties.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="train-class-cohort">
            Năm khóa
          </label>
          <input
            id="train-class-cohort"
            className="field__input"
            type="number"
            min={1990}
            max={2100}
            value={cohortYear}
            onChange={(e) => setCohortYear(e.target.value)}
            placeholder="VD: 2025"
          />
        </div>

        {error && (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        )}

        <div className="train-dlg__actions">
          <button type="submit" className="btn btn--primary" disabled={saving}>
            {saving ? 'Đang lưu…' : editing ? 'Lưu thay đổi' : 'Thêm lớp'}
          </button>
          <button
            type="button"
            className="btn btn--ghost"
            disabled={saving}
            onClick={() => dialogRef.current?.close()}
          >
            Hủy
          </button>
        </div>
      </form>
    </TrainingDialog>
  );
}

/**
 * Form thêm / sửa môn học. Ô chọn giảng viên liệt kê mọi giảng viên kèm số môn
 * đang phụ trách; lựa chọn "— Chưa phân công —" gán `lecturerId: null`.
 */
export function CourseDialog({
  initial,
  lecturers,
  openRef,
  onClose,
  onSaved,
}: {
  initial: CourseItem | null;
  lecturers: LecturerItem[];
  openRef: React.RefObject<HTMLElement | null>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [code, setCode] = useState(initial?.code ?? '');
  const [name, setName] = useState(initial?.name ?? '');
  const [credits, setCredits] = useState(
    initial ? String(initial.credits) : '',
  );
  const [description, setDescription] = useState(initial?.description ?? '');
  const [lecturerId, setLecturerId] = useState(initial?.lecturer?.id ?? '');
  const [facultyId, setFacultyId] = useState(initial?.facultyId ?? '');
  const [faculties, setFaculties] = useState<FacultyItem[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  const editing = initial != null;

  useEffect(() => {
    facultyApi
      .list()
      .then((r) => setFaculties(r.items))
      .catch(() => setFaculties([]));
  }, []);

  // Nếu môn đã có khoa thì chỉ hiện giảng viên cùng khoa; chưa có khoa thì hiện tất cả.
  const visibleLecturers = facultyId
    ? lecturers.filter((l) => l.facultyId === facultyId)
    : lecturers;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (saving) return;
    setSaving(true);
    setError(null);
    const payload = {
      code: code.trim(),
      name: name.trim(),
      credits: Number(credits),
      description: description.trim() || null,
      lecturerId: lecturerId || null,
      facultyId: facultyId || null,
    };
    try {
      if (editing && initial) {
        // Mã khóa khi sửa; vẫn gửi để giữ hợp đồng PATCH ổn định.
        await catalogApi.updateCourse(initial.id, {
          name: payload.name,
          credits: payload.credits,
          description: payload.description,
          lecturerId: payload.lecturerId,
          facultyId: payload.facultyId,
        });
      } else {
        await catalogApi.createCourse(payload);
      }
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không lưu được môn học.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <TrainingDialog
      openRef={openRef}
      title={editing ? 'Sửa môn học' : 'Thêm môn học'}
      titleId="train-course-title"
      onClose={onClose}
      forwardRef={dialogRef}
    >
      <form onSubmit={(e) => void submit(e)}>
        <div className="field">
          <label className="field__label" htmlFor="train-course-code">
            Mã môn<span className="req">*</span>
          </label>
          <input
            id="train-course-code"
            className="field__input"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            disabled={editing}
            required
            placeholder="VD: ANM301"
          />
          {editing && (
            <span className="field__hint">Mã môn không thể đổi sau khi đã tạo.</span>
          )}
        </div>

        <div className="field">
          <label className="field__label" htmlFor="train-course-name">
            Tên môn<span className="req">*</span>
          </label>
          <input
            id="train-course-name"
            className="field__input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="VD: An ninh mạng ứng dụng"
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="train-course-credits">
            Tín chỉ<span className="req">*</span>
          </label>
          <input
            id="train-course-credits"
            className="field__input"
            type="number"
            min={1}
            max={20}
            value={credits}
            onChange={(e) => setCredits(e.target.value)}
            required
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="train-course-desc">
            Mô tả
          </label>
          <textarea
            id="train-course-desc"
            className="field__input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="Nội dung chính của môn…"
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="train-course-faculty">
            Khoa
          </label>
          <select
            id="train-course-faculty"
            className="field__input"
            value={facultyId}
            onChange={(e) => {
              setFacultyId(e.target.value);
              // Đổi khoa thì reset giảng viên nếu người cũ không thuộc khoa mới.
              const next = e.target.value;
              if (lecturerId && next) {
                const stillVisible = lecturers.some((l) => l.id === lecturerId && l.facultyId === next);
                if (!stillVisible) setLecturerId('');
              }
            }}
          >
            <option value="">— Chưa xếp khoa —</option>
            {faculties.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="train-course-lecturer">
            Giảng viên phụ trách
          </label>
          <select
            id="train-course-lecturer"
            className="field__input"
            value={lecturerId}
            onChange={(e) => setLecturerId(e.target.value)}
          >
            <option value="">— Chưa phân công —</option>
            {visibleLecturers.map((l) => (
              <option key={l.id} value={l.id}>
                {l.fullName} — {l.courseCount} môn
              </option>
            ))}
          </select>
        </div>

        {error && (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        )}

        <div className="train-dlg__actions">
          <button type="submit" className="btn btn--primary" disabled={saving}>
            {saving ? 'Đang lưu…' : editing ? 'Lưu thay đổi' : 'Thêm môn'}
          </button>
          <button
            type="button"
            className="btn btn--ghost"
            disabled={saving}
            onClick={() => dialogRef.current?.close()}
          >
            Hủy
          </button>
        </div>
      </form>
    </TrainingDialog>
  );
}

/**
 * Hộp thoại xác nhận xóa (lớp / môn). Lỗi 409 (đang dùng) hiện nguyên
 * `message` của API trong hộp thoại, không đóng — người dùng thấy lý do.
 */
export function ConfirmDeleteDialog({
  openRef,
  title,
  message,
  busy,
  error,
  onConfirm,
  onClose,
}: {
  openRef: React.RefObject<HTMLElement | null>;
  title: string;
  message: string;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <TrainingDialog
      openRef={openRef}
      title={title}
      titleId="train-confirm-title"
      onClose={onClose}
    >
      <p className="train-confirm__msg">{message}</p>
      {error && (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      )}
      <div className="train-dlg__actions">
        <button
          type="button"
          className="btn btn--danger"
          disabled={busy}
          onClick={onConfirm}
        >
          {busy ? 'Đang xóa…' : 'Xóa'}
        </button>
        <button type="button" className="btn btn--ghost" disabled={busy} onClick={onClose}>
          Hủy
        </button>
      </div>
    </TrainingDialog>
  );
}

/**
 * Hộp thoại đổi lớp cho một học viên. Chọn một lớp hoặc "Bỏ lớp" để tách học
 * viên ra khỏi mọi lớp.
 */
export function AssignClassDialog({
  student,
  classes,
  openRef,
  onClose,
  onSaved,
}: {
  student: { id: string; fullName: string; studentCode: string; class: { id: string } | null };
  classes: ClassItem[];
  openRef: React.RefObject<HTMLElement | null>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [classId, setClassId] = useState(student.class?.id ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  async function submit() {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      await catalogApi.setStudentClass(student.id, classId || null);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không đổi được lớp.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <TrainingDialog
      openRef={openRef}
      title={`Đổi lớp — ${student.fullName}`}
      titleId="train-assign-title"
      onClose={onClose}
      forwardRef={dialogRef}
    >
      <p className="train-assign__who mono">{student.studentCode}</p>
      <div className="field">
        <label className="field__label" htmlFor="train-assign-class">
          Lớp
        </label>
        <select
          id="train-assign-class"
          className="field__input"
          value={classId}
          onChange={(e) => setClassId(e.target.value)}
        >
          <option value="">— Bỏ lớp —</option>
          {classes.map((c) => (
            <option key={c.id} value={c.id}>
              {c.code} — {c.name}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      )}

      <div className="train-dlg__actions">
        <button type="button" className="btn btn--primary" disabled={saving} onClick={() => void submit()}>
          {saving ? 'Đang lưu…' : 'Lưu'}
        </button>
        <button type="button" className="btn btn--ghost" disabled={saving} onClick={onClose}>
          Hủy
        </button>
      </div>
    </TrainingDialog>
  );
}
