import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '@/services/api';
import { catalogApi, type CourseItem, type LecturerItem } from '@/services/catalog-api';
import { facultyApi, type FacultyItem } from '@/services/faculty-api';
import { TrainingDialog } from './Dialogs';

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
