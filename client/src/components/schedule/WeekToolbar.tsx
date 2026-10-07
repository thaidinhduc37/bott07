import { Icon } from '@/components/shared/Icon';
import { dateOf, type CourseRef } from '@/services/schedule-api';

/**
 * Thanh điều hướng tuần của lịch học: một hàng gồm nhóm "‹ Hôm nay ›", khoảng ngày của tuần đang xem,
 * rồi bộ lọc môn và công tắc hiện lịch thi ở bên phải. Bề rộng hẹp thì tự xuống dòng.
 */
export function WeekToolbar({
  weekStart,
  isCurrentWeek,
  onShift,
  onToday,
  courses,
  courseId,
  onCourse,
  showExams,
  onShowExams,
}: {
  weekStart: Date;
  isCurrentWeek: boolean;
  onShift: (deltaWeeks: number) => void;
  onToday: () => void;
  courses: CourseRef[];
  courseId: string;
  onCourse: (id: string) => void;
  showExams: boolean;
  onShowExams: (v: boolean) => void;
}) {
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekStart.getDate() + 6);

  return (
    <div className="sheet week-bar">
      <div className="week-bar__nav">
        <div className="week-bar__group" role="group" aria-label="Chuyển tuần">
          <button type="button" className="week-bar__btn" onClick={() => onShift(-1)} aria-label="Tuần trước">
            <Icon name="chevronLeft" size={18} />
          </button>
          <button
            type="button"
            className={`week-bar__today${isCurrentWeek ? ' week-bar__today--on' : ''}`}
            onClick={onToday}
          >
            Hôm nay
          </button>
          <button type="button" className="week-bar__btn" onClick={() => onShift(1)} aria-label="Tuần tới">
            <Icon name="chevronRight" size={18} />
          </button>
        </div>
        <span className="week-bar__range mono">
          {dateOf(weekStart.toISOString())} – {dateOf(weekEnd.toISOString())}
        </span>
      </div>

      <div className="week-bar__filters">
        <select
          className="field__input week-bar__select"
          value={courseId}
          onChange={(e) => onCourse(e.target.value)}
          aria-label="Lọc theo môn học"
        >
          <option value="">Tất cả môn học</option>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>
              {c.code} — {c.name}
            </option>
          ))}
        </select>

        <label className="switch-field">
          <span className="switch">
            <input type="checkbox" checked={showExams} onChange={(e) => onShowExams(e.target.checked)} />
            <span className="switch__track" aria-hidden="true">
              <span className="switch__thumb" />
            </span>
          </span>
          <span className="week-bar__switch-label">Hiện cả lịch thi</span>
        </label>
      </div>
    </div>
  );
}
