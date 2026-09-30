import { timeOf, type Conflict } from '@/services/schedule-api';

/** Nhãn ngắn cho từng loại va chạm lịch. */
const KIND_LABEL: Record<Conflict['kind'], string> = {
  CLASS: 'Trùng lớp',
  ROOM: 'Trùng phòng',
  LECTURER: 'Trùng giảng viên',
};

/**
 * Danh sách va chạm lịch mà backend trả về trong lỗi 409 `SCHEDULE_CONFLICT`.
 * Mỗi dòng: "Trùng lớp / Trùng phòng / Trùng giảng viên với <môn> · lớp <lớp> · <giờ>".
 * Hiển thị trong form để người dùng sửa dữ liệu rồi lưu lại.
 */
export function ConflictList({ conflicts }: { conflicts: Conflict[] }) {
  if (conflicts.length === 0) return null;

  return (
    <div className="notice notice--error sedit-conflicts" role="alert">
      <p className="sedit-conflicts__head">
        {conflicts.length} chỗ trùng lịch — sửa thông tin rồi lưu lại.
      </p>
      <ul className="sedit-conflicts__list">
        {conflicts.map((c, i) => (
          <li key={`${c.kind}-${c.id}-${i}`}>
            <span className={`tag ${c.kind === 'CLASS' ? 'tag--warn' : c.kind === 'ROOM' ? 'tag--seal' : 'tag--pen'}`}>
              {KIND_LABEL[c.kind]}
            </span>
            <span className="sedit-conflicts__text">
              với {c.course.code} — {c.course.name}
              {c.class.code ? ` · lớp ${c.class.code}` : ''}
              {c.room ? ` · ${c.room}` : ''} · {timeOf(c.startsAt)}–{timeOf(c.endsAt)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
