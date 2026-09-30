import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { ApiError } from '@/services/api';
import {
  scheduleApi,
  type AvailabilityRoom,
  type ClassRef,
  type Conflict,
  type CourseWithLecturer,
  type CreateExamInput,
  type Exam,
  type UpdateExamInput,
} from '@/services/schedule-api';
import { ConflictList } from '@/components/schedule/ConflictList';
import { useAvailability } from '@/components/schedule/useAvailability';

/** Hình thức thi — giá trị + nhãn đúng như backend (`ExamFormat`). */
const EXAM_FORMATS: { value: string; label: string }[] = [
  { value: 'TRAC_NGHIEM', label: 'Trắc nghiệm' },
  { value: 'TU_LUAN', label: 'Tự luận' },
  { value: 'THUC_HANH', label: 'Thực hành' },
  { value: 'KET_HOP', label: 'Kết hợp' },
];

const ACADEMIC_YEARS = ['2025–2026', '2026–2027', '2027–2028'];
const SEMESTERS = ['Học kỳ 1', 'Học kỳ 2', 'Học kỳ 3'];

interface Props {
  classes: ClassRef[];
  courses: CourseWithLecturer[];
  /** Ca thi đang sửa — `null` nghĩa là tạo mới (khi đó chọn được lớp). */
  exam: Exam | null;
  onSaved: (e: Exam) => void;
  onCancel: () => void;
}

/** "HH:mm" theo giờ Việt Nam từ một mốc ISO — để điền sẵn ô giờ khi sửa. */
const vnTime = (iso: string) =>
  new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Ho_Chi_Minh' }).format(
    new Date(iso),
  );

/** Nhãn gợi ý phòng: "A201 · Nhà A · 60 chỗ" + "chưa trong danh mục" khi cần. */
function roomSuggestionLabel(r: AvailabilityRoom): string {
  const parts = [r.room];
  if (r.building) parts.push(r.building);
  if (r.capacity != null) parts.push(`${r.capacity} chỗ`);
  let label = parts.join(' · ');
  if (!r.registered) label += ' · chưa trong danh mục';
  return label;
}

export function ExamForm({ classes, courses, exam, onSaved, onCancel }: Props) {
  const isEdit = exam !== null;

  const [classId, setClassId] = useState(exam?.class?.id ?? '');
  const [courseId, setCourseId] = useState(exam?.course.id ?? '');
  const [academicYear, setAcademicYear] = useState(exam?.academicYear ?? '');
  const [semester, setSemester] = useState(exam?.semester ?? '');
  const [examDate, setExamDate] = useState(exam?.examDate ?? '');
  const [startTime, setStartTime] = useState(exam ? vnTime(exam.startsAt) : '');
  const [durationMinutes, setDurationMinutes] = useState(exam ? String(exam.durationMinutes) : '90');
  const [room, setRoom] = useState(exam?.room ?? '');
  const [building, setBuilding] = useState(exam?.building ?? '');
  const [examFormat, setExamFormat] = useState(exam?.examFormat ?? 'TU_LUAN');
  const [allowedMaterials, setAllowedMaterials] = useState(exam?.allowedMaterials ?? '');
  const [candidateCount, setCandidateCount] = useState(
    exam?.candidateCount != null ? String(exam.candidateCount) : '',
  );
  const [chiefProctor, setChiefProctor] = useState(exam?.chiefProctor ?? '');
  const [secondProctor, setSecondProctor] = useState(exam?.secondProctor ?? '');
  const [note, setNote] = useState(exam?.note ?? '');

  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Khoảng giờ = giờ bắt đầu + thời lượng (phút) để hỏi phòng rảnh.
  const endTime = useMemo(() => {
    if (!startTime) return '';
    const [h, m] = startTime.split(':').map(Number);
    const total = h * 60 + m + (Number(durationMinutes) || 0);
    const eh = Math.floor(total / 60) % 24;
    const em = total % 60;
    return `${String(eh).padStart(2, '0')}:${String(em).padStart(2, '0')}`;
  }, [startTime, durationMinutes]);

  const { data: avail } = useAvailability(examDate, startTime, endTime, exam?.id);

  useEffect(() => {
    if (isEdit) return;
    setAcademicYear((cur) => cur || '2026–2027');
    setSemester((cur) => cur || 'Học kỳ 2');
  }, [isEdit]);

  const freeRooms = useMemo(() => (avail?.rooms ?? []).filter((r) => !r.busy), [avail]);

  // Phòng nhập khớp danh mục (theo mã, không phân biệt hoa thường) — để tự điền
  // tòa nhà, hiện sức chứa, và cảnh báo khi số thí sinh vượt sức chứa.
  const matchedRoom = useMemo(() => {
    const q = room.trim().toLowerCase();
    if (!q) return null;
    return (avail?.rooms ?? []).find((r) => r.room.toLowerCase() === q) ?? null;
  }, [avail, room]);

  const overCapacity =
    matchedRoom?.capacity != null &&
    candidateCount.trim() !== '' &&
    Number(candidateCount) > (matchedRoom?.capacity ?? 0);

  function handleRoomChange(value: string) {
    setRoom(value);
    // Phòng khớp danh mục + có tòa nhà + ô tòa đang trống → tự điền.
    const q = value.trim().toLowerCase();
    if (!q) return;
    const m = (avail?.rooms ?? []).find((r) => r.room.toLowerCase() === q);
    if (m?.building) setBuilding((cur) => (cur.trim() === '' ? m.building! : cur));
  }

  function validate(): string | null {
    if (!classId) return 'Chọn lớp.';
    if (!courseId) return 'Chọn môn.';
    if (!academicYear.trim()) return 'Nhập năm học.';
    if (!semester.trim()) return 'Nhập học kỳ.';
    if (!examDate) return 'Chọn ngày thi.';
    if (!startTime) return 'Nhập giờ bắt đầu.';
    const dur = Number(durationMinutes);
    if (!Number.isInteger(dur) || dur <= 0) return 'Thời lượng phải là số phút dương.';
    if (!room.trim()) return 'Nhập phòng.';
    return null;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const v = validate();
    if (v) {
      setError(v);
      return;
    }
    setSaving(true);
    setError(null);
    setConflicts([]);

    const base = {
      courseId,
      academicYear: academicYear.trim(),
      semester: semester.trim(),
      examDate,
      startTime,
      durationMinutes: Number(durationMinutes),
      room: room.trim(),
      building: building.trim() || null,
      examFormat,
      allowedMaterials: allowedMaterials.trim() || null,
      candidateCount: candidateCount.trim() === '' ? null : Number(candidateCount),
      chiefProctor: chiefProctor.trim() || null,
      secondProctor: secondProctor.trim() || null,
      note: note.trim() || null,
    };

    try {
      const saved = isEdit
        ? await scheduleApi.updateExam(exam!.id, base as UpdateExamInput)
        : await scheduleApi.createExam({ classId, ...base } as CreateExamInput);
      onSaved(saved);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && err.code === 'SCHEDULE_CONFLICT') {
        setConflicts((err.details?.conflicts as Conflict[] | undefined) ?? []);
        setError('Ca thi này trùng với lịch hiện có.');
      } else {
        setError(err instanceof ApiError ? err.message : 'Không lưu được. Thử lại.');
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="sedit-form" onSubmit={(e) => void submit(e)}>
      {conflicts.length > 0 && <ConflictList conflicts={conflicts} />}
      {error && conflicts.length === 0 && (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      )}

      <div className="sedit-grid">
        <div className="field">
          <label className="field__label" htmlFor="sexam-class">
            Lớp{!isEdit && <span className="req">*</span>}
          </label>
          <select
            id="sexam-class"
            className="field__input"
            value={classId}
            disabled={isEdit}
            onChange={(e) => setClassId(e.target.value)}
          >
            {isEdit ? (
              <option value={classId}>{exam!.class?.code ?? '—'}</option>
            ) : (
              <>
                <option value="">— chọn lớp —</option>
                {classes.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code} — {c.name}
                  </option>
                ))}
              </>
            )}
          </select>
          {isEdit && <span className="field__hint">Lớp không đổi được khi sửa ca thi.</span>}
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sexam-course">
            Môn<span className="req">*</span>
          </label>
          <select
            id="sexam-course"
            className="field__input"
            value={courseId}
            onChange={(e) => setCourseId(e.target.value)}
          >
            <option value="">— chọn môn —</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} — {c.name}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sexam-year">
            Năm học<span className="req">*</span>
          </label>
          <input
            id="sexam-year"
            className="field__input"
            list="sexam-year-list"
            value={academicYear}
            onChange={(e) => setAcademicYear(e.target.value)}
            placeholder="2026–2027"
          />
          <datalist id="sexam-year-list">
            {ACADEMIC_YEARS.map((y) => (
              <option key={y} value={y} />
            ))}
          </datalist>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sexam-semester">
            Học kỳ<span className="req">*</span>
          </label>
          <select
            id="sexam-semester"
            className="field__input"
            value={semester}
            onChange={(e) => setSemester(e.target.value)}
          >
            <option value="">— chọn học kỳ —</option>
            {SEMESTERS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sexam-date">
            Ngày thi<span className="req">*</span>
          </label>
          <input
            id="sexam-date"
            type="date"
            className="field__input"
            value={examDate}
            onChange={(e) => setExamDate(e.target.value)}
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sexam-starttime">
            Giờ bắt đầu<span className="req">*</span>
          </label>
          <input
            id="sexam-starttime"
            type="time"
            className="field__input"
            value={startTime}
            onChange={(e) => setStartTime(e.target.value)}
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sexam-duration">
            Thời lượng (phút)<span className="req">*</span>
          </label>
          <input
            id="sexam-duration"
            type="number"
            min={1}
            className="field__input"
            value={durationMinutes}
            onChange={(e) => setDurationMinutes(e.target.value)}
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sexam-room">
            Phòng<span className="req">*</span>
          </label>
          <input
            id="sexam-room"
            className="field__input"
            list="sexam-room-list"
            value={room}
            onChange={(e) => handleRoomChange(e.target.value)}
            placeholder="vd A201"
          />
          <datalist id="sexam-room-list">
            {freeRooms.map((r) => (
              <option key={`${r.room}-${r.building ?? ''}`} value={r.room}>
                {roomSuggestionLabel(r)}
              </option>
            ))}
          </datalist>
          {overCapacity && (
            <span className="tag tag--warn" role="alert">
              Số thí sinh vượt sức chứa phòng ({matchedRoom?.capacity} chỗ)
            </span>
          )}
          {matchedRoom?.capacity != null && !overCapacity && (
            <span className="field__hint">Sức chứa: {matchedRoom.capacity} chỗ.</span>
          )}
          {freeRooms.length > 0 && (
            <span className="field__hint">{freeRooms.length} phòng rảnh trong khung giờ này.</span>
          )}
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sexam-building">
            Tòa nhà
          </label>
          <input
            id="sexam-building"
            className="field__input"
            value={building}
            onChange={(e) => setBuilding(e.target.value)}
            placeholder="vd Tòa A"
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sexam-format">
            Hình thức thi
          </label>
          <select
            id="sexam-format"
            className="field__input"
            value={examFormat}
            onChange={(e) => setExamFormat(e.target.value)}
          >
            {EXAM_FORMATS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sexam-materials">
            Được mang vào
          </label>
          <input
            id="sexam-materials"
            className="field__input"
            value={allowedMaterials}
            onChange={(e) => setAllowedMaterials(e.target.value)}
            placeholder="vd giấy A4, máy tính không kết nối mạng"
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sexam-candidates">
            Số thí sinh
          </label>
          <input
            id="sexam-candidates"
            type="number"
            min={0}
            className="field__input"
            value={candidateCount}
            onChange={(e) => setCandidateCount(e.target.value)}
            placeholder="tùy chọn"
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sexam-chief">
            Giám thị 1
          </label>
          <input
            id="sexam-chief"
            className="field__input"
            value={chiefProctor}
            onChange={(e) => setChiefProctor(e.target.value)}
            placeholder="tên giám thị chính"
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sexam-second">
            Giám thị 2
          </label>
          <input
            id="sexam-second"
            className="field__input"
            value={secondProctor}
            onChange={(e) => setSecondProctor(e.target.value)}
            placeholder="tên giám thị phụ"
          />
        </div>

        <div className="field sedit-field--full">
          <label className="field__label" htmlFor="sexam-note">
            Ghi chú
          </label>
          <textarea
            id="sexam-note"
            className="field__input"
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="ghi chú cho ca thi này…"
          />
        </div>
      </div>

      <div className="sedit-actions">
        <button type="submit" className="btn btn--primary" disabled={saving}>
          {saving ? 'Đang lưu…' : isEdit ? 'Lưu thay đổi' : 'Thêm ca thi'}
        </button>
        <button type="button" className="btn btn--ghost" onClick={onCancel} disabled={saving}>
          Hủy
        </button>
      </div>
    </form>
  );
}
