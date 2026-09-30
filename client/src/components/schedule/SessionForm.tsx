import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { ApiError } from '@/services/api';
import {
  scheduleApi,
  type AvailabilityRoom,
  type ClassRef,
  type Conflict,
  type CourseWithLecturer,
  type CreateSessionInput,
  type Session,
  type UpdateSessionInput,
} from '@/services/schedule-api';
import { ConflictList } from '@/components/schedule/ConflictList';
import { useAvailability } from '@/components/schedule/useAvailability';

/** Loại buổi học — giá trị + nhãn đúng như backend (`SessionType`). */
const SESSION_TYPES: { value: string; label: string }[] = [
  { value: 'LY_THUYET', label: 'Lý thuyết' },
  { value: 'THUC_HANH', label: 'Thực hành' },
  { value: 'KIEM_TRA_GIUA_KY', label: 'Kiểm tra giữa kỳ' },
  { value: 'ON_TAP', label: 'Ôn tập' },
  { value: 'HOC_BU', label: 'Học bù' },
];

/** Năm học phổ biến — cho phép nhập tự do nếu không có trong danh sách. */
const ACADEMIC_YEARS = ['2025–2026', '2026–2027', '2027–2028'];
const SEMESTERS = ['Học kỳ 1', 'Học kỳ 2', 'Học kỳ 3'];

const PERIODS = Array.from({ length: 20 }, (_, i) => i + 1);

interface Props {
  classes: ClassRef[];
  courses: CourseWithLecturer[];
  /** Buổi đang sửa — `null` nghĩa là tạo mới (khi đó chọn được lớp). */
  session: Session | null;
  onSaved: (s: Session) => void;
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

export function SessionForm({ classes, courses, session, onSaved, onCancel }: Props) {
  const isEdit = session !== null;

  const [classId, setClassId] = useState(session?.class?.id ?? '');
  const [courseId, setCourseId] = useState(session?.course.id ?? '');
  const [academicYear, setAcademicYear] = useState(session?.academicYear ?? '');
  const [semester, setSemester] = useState(session?.semester ?? '');
  const [sessionDate, setSessionDate] = useState(session?.sessionDate ?? '');
  const [startPeriod, setStartPeriod] = useState(session ? String(session.startPeriod) : '1');
  const [endPeriod, setEndPeriod] = useState(session ? String(session.endPeriod) : '1');
  const [startTime, setStartTime] = useState(session ? vnTime(session.startsAt) : '');
  const [endTime, setEndTime] = useState(session ? vnTime(session.endsAt) : '');
  const [room, setRoom] = useState(session?.room ?? '');
  const [building, setBuilding] = useState(session?.building ?? '');
  const [instructor, setInstructor] = useState(session?.instructor ?? '');
  const [deliveryMode, setDeliveryMode] = useState(session?.deliveryMode ?? '');
  const [sessionType, setSessionType] = useState(session?.sessionType ?? 'LY_THUYET');
  const [note, setNote] = useState(session?.note ?? '');
  const [weekNumber, setWeekNumber] = useState(session?.weekNumber != null ? String(session.weekNumber) : '');

  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const { data: avail } = useAvailability(sessionDate, startTime, endTime, session?.id);

  // Điền năm học / học kỳ khi mở form sửa — backend không trả hai trường này
  // trong `Session` nên giữ giá trị người dùng đã nhập (rỗng nếu không nhập lại).
  useEffect(() => {
    if (isEdit) return;
    // Tạo mới: mặc định năm học hiện hành.
    setAcademicYear((cur) => cur || '2026–2027');
    setSemester((cur) => cur || 'Học kỳ 1');
  }, [isEdit]);

  const selectedCourse = useMemo(
    () => courses.find((c) => c.id === courseId) ?? null,
    [courses, courseId],
  );

  // Phòng rảnh trong khoảng giờ đã chọn (chỉ gợi ý, không bắt buộc).
  const freeRooms = useMemo(
    () => (avail?.rooms ?? []).filter((r) => !r.busy),
    [avail],
  );
  const busyLecturer = useMemo(
    () =>
      selectedCourse?.lecturer
        ? (avail?.lecturers ?? []).find((l) => l.id === selectedCourse.lecturer!.id && l.busy) ?? null
        : null,
    [avail, selectedCourse],
  );

  // Phòng nhập khớp danh mục (theo mã, không phân biệt hoa thường) — để tự điền
  // tòa nhà và hiện sức chứa.
  const matchedRoom = useMemo(() => {
    const q = room.trim().toLowerCase();
    if (!q) return null;
    return (avail?.rooms ?? []).find((r) => r.room.toLowerCase() === q) ?? null;
  }, [avail, room]);

  function handleCourseChange(id: string) {
    setCourseId(id);
    // Khi chọn môn có giảng viên phụ trách, gợi ý tên người đứng lớp.
    const c = courses.find((x) => x.id === id);
    if (c?.lecturer) setInstructor(c.lecturer.fullName);
  }

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
    if (!sessionDate) return 'Chọn ngày.';
    if (!startTime) return 'Nhập giờ bắt đầu.';
    if (!endTime) return 'Nhập giờ kết thúc.';
    if (endTime <= startTime) return 'Giờ kết thúc phải sau giờ bắt đầu.';
    const sp = Number(startPeriod);
    const ep = Number(endPeriod);
    if (!Number.isInteger(sp) || sp < 1 || sp > 20) return 'Tiết bắt đầu phải từ 1 đến 20.';
    if (!Number.isInteger(ep) || ep < 1 || ep > 20) return 'Tiết kết thúc phải từ 1 đến 20.';
    if (ep < sp) return 'Tiết kết thúc phải lớn hơn hoặc bằng tiết bắt đầu.';
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
      sessionDate,
      weekNumber: weekNumber.trim() === '' ? null : Number(weekNumber),
      startPeriod: Number(startPeriod),
      endPeriod: Number(endPeriod),
      startTime,
      endTime,
      room: room.trim(),
      building: building.trim() || null,
      instructor: instructor.trim() || null,
      deliveryMode: deliveryMode.trim() || null,
      sessionType,
      note: note.trim() || null,
    };

    try {
      const saved = isEdit
        ? await scheduleApi.updateSession(session!.id, base as UpdateSessionInput)
        : await scheduleApi.createSession({ classId, ...base } as CreateSessionInput);
      onSaved(saved);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && err.code === 'SCHEDULE_CONFLICT') {
        setConflicts((err.details?.conflicts as Conflict[] | undefined) ?? []);
        setError('Buổi này trùng với lịch hiện có.');
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
          <label className="field__label" htmlFor="sedit-class">
            Lớp{!isEdit && <span className="req">*</span>}
          </label>
          <select
            id="sedit-class"
            className="field__input"
            value={classId}
            disabled={isEdit}
            onChange={(e) => setClassId(e.target.value)}
          >
            {isEdit ? (
              <option value={classId}>{session!.class?.code ?? '—'}</option>
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
          {isEdit && <span className="field__hint">Lớp không đổi được khi sửa buổi.</span>}
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sedit-course">
            Môn<span className="req">*</span>
          </label>
          <select
            id="sedit-course"
            className="field__input"
            value={courseId}
            onChange={(e) => handleCourseChange(e.target.value)}
          >
            <option value="">— chọn môn —</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} — {c.name}
              </option>
            ))}
          </select>
          <span className="field__hint">
            {selectedCourse?.lecturer
              ? `Giảng viên: ${selectedCourse.lecturer.fullName}`
              : 'Môn này chưa có giảng viên phụ trách'}
          </span>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sedit-year">
            Năm học<span className="req">*</span>
          </label>
          <input
            id="sedit-year"
            className="field__input"
            list="sedit-year-list"
            value={academicYear}
            onChange={(e) => setAcademicYear(e.target.value)}
            placeholder="2026–2027"
          />
          <datalist id="sedit-year-list">
            {ACADEMIC_YEARS.map((y) => (
              <option key={y} value={y} />
            ))}
          </datalist>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sedit-semester">
            Học kỳ<span className="req">*</span>
          </label>
          <select
            id="sedit-semester"
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
          <label className="field__label" htmlFor="sedit-date">
            Ngày<span className="req">*</span>
          </label>
          <input
            id="sedit-date"
            type="date"
            className="field__input"
            value={sessionDate}
            onChange={(e) => setSessionDate(e.target.value)}
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sedit-week">
            Tuần
          </label>
          <input
            id="sedit-week"
            type="number"
            min={1}
            className="field__input"
            value={weekNumber}
            onChange={(e) => setWeekNumber(e.target.value)}
            placeholder="tùy chọn"
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sedit-starttime">
            Giờ bắt đầu<span className="req">*</span>
          </label>
          <input
            id="sedit-starttime"
            type="time"
            className="field__input"
            value={startTime}
            onChange={(e) => setStartTime(e.target.value)}
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sedit-endtime">
            Giờ kết thúc<span className="req">*</span>
          </label>
          <input
            id="sedit-endtime"
            type="time"
            className="field__input"
            value={endTime}
            onChange={(e) => setEndTime(e.target.value)}
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sedit-startperiod">
            Tiết bắt đầu<span className="req">*</span>
          </label>
          <select
            id="sedit-startperiod"
            className="field__input"
            value={startPeriod}
            onChange={(e) => setStartPeriod(e.target.value)}
          >
            {PERIODS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sedit-endperiod">
            Tiết kết thúc<span className="req">*</span>
          </label>
          <select
            id="sedit-endperiod"
            className="field__input"
            value={endPeriod}
            onChange={(e) => setEndPeriod(e.target.value)}
          >
            {PERIODS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sedit-room">
            Phòng<span className="req">*</span>
          </label>
          <input
            id="sedit-room"
            className="field__input"
            list="sedit-room-list"
            value={room}
            onChange={(e) => handleRoomChange(e.target.value)}
            placeholder="vd A201"
          />
          <datalist id="sedit-room-list">
            {freeRooms.map((r) => (
              <option key={`${r.room}-${r.building ?? ''}`} value={r.room}>
                {roomSuggestionLabel(r)}
              </option>
            ))}
          </datalist>
          {busyLecturer && (
            <span className="field__error">
              Giảng viên {selectedCourse?.lecturer?.fullName} đang bận lúc này.
            </span>
          )}
          {matchedRoom?.capacity != null && (
            <span className="field__hint">Sức chứa: {matchedRoom.capacity} chỗ.</span>
          )}
          {freeRooms.length > 0 && !busyLecturer && (
            <span className="field__hint">
              {freeRooms.length} phòng rảnh trong khung giờ này.
            </span>
          )}
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sedit-building">
            Tòa nhà
          </label>
          <input
            id="sedit-building"
            className="field__input"
            value={building}
            onChange={(e) => setBuilding(e.target.value)}
            placeholder="vd Tòa A"
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sedit-instructor">
            Người đứng lớp
          </label>
          <input
            id="sedit-instructor"
            className="field__input"
            value={instructor}
            onChange={(e) => setInstructor(e.target.value)}
            placeholder="tên người dạy buổi này"
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sedit-delivery">
            Hình thức học
          </label>
          <input
            id="sedit-delivery"
            className="field__input"
            value={deliveryMode}
            onChange={(e) => setDeliveryMode(e.target.value)}
            placeholder="vd Trực tiếp / Trực tuyến"
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="sedit-type">
            Loại buổi
          </label>
          <select
            id="sedit-type"
            className="field__input"
            value={sessionType}
            onChange={(e) => setSessionType(e.target.value)}
          >
            {SESSION_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div className="field sedit-field--full">
          <label className="field__label" htmlFor="sedit-note">
            Ghi chú
          </label>
          <textarea
            id="sedit-note"
            className="field__input"
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="ghi chú cho buổi này…"
          />
        </div>
      </div>

      <div className="sedit-actions">
        <button type="submit" className="btn btn--primary" disabled={saving}>
          {saving ? 'Đang lưu…' : isEdit ? 'Lưu thay đổi' : 'Thêm buổi học'}
        </button>
        <button type="button" className="btn btn--ghost" onClick={onCancel} disabled={saving}>
          Hủy
        </button>
      </div>
    </form>
  );
}
