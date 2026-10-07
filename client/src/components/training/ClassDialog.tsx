import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '@/services/api';
import { catalogApi, type ClassItem } from '@/services/catalog-api';
import { facultyApi, type FacultyItem } from '@/services/faculty-api';
import { TrainingDialog } from './Dialogs';

/**
 * Form thêm / sửa lớp. Khi `initial` có giá trị là chế độ sửa: mã khóa lại,
 * title đổi thành "Sửa lớp". Lỗi 409 (mã trùng) hiện nguyên `message` của API.
 */
export function ClassDialog({
  initial,
  majors,
  openRef,
  onClose,
  onSaved,
}: {
  initial: ClassItem | null;
  /** Các ngành đã có, gợi ý khi nhập ngành. */
  majors: string[];
  openRef: React.RefObject<HTMLElement | null>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [code, setCode] = useState(initial?.code ?? '');
  const [name, setName] = useState(initial?.name ?? '');
  const [facultyId, setFacultyId] = useState(initial?.facultyId ?? '');
  const [major, setMajor] = useState(initial?.major ?? '');
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
      major: major.trim() || null,
      cohortYear: cohortYear.trim() ? Number(cohortYear) : null,
    };
    try {
      if (editing && initial) {
        // Chế độ sửa: mã không đổi, chỉ gửi các trường cho phép sửa.
        await catalogApi.updateClass(initial.id, {
          name: payload.name,
          facultyId: payload.facultyId,
          major: payload.major,
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
          <label className="field__label" htmlFor="train-class-major">
            Ngành
          </label>
          <input
            id="train-class-major"
            className="field__input"
            list="train-class-majors"
            value={major}
            maxLength={200}
            onChange={(e) => setMajor(e.target.value)}
            placeholder="VD: An toàn thông tin"
          />
          <datalist id="train-class-majors">
            {majors.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
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
