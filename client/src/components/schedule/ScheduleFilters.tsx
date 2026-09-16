import { dateOf } from '@/services/schedule-api';
import type { CourseRef } from '@/services/schedule-api';

export function ScheduleFilters({
  weekStart,
  weekEnd,
  courses,
  courseId,
  onCourseChange,
  showExams,
  onToggleExams,
  onShift,
  onToday,
}: {
  weekStart: Date;
  weekEnd: Date;
  courses: CourseRef[];
  courseId: string;
  onCourseChange: (id: string) => void;
  showExams: boolean;
  onToggleExams: (v: boolean) => void;
  onShift: (delta: number) => void;
  onToday: () => void;
}) {
  return (
    <div className="sheet" style={{ padding: '0.85rem 1.1rem' }}>
      <div className="spread">
        <div className="row">
          <button type="button" className="btn btn--ghost" onClick={() => onShift(-1)}>
            ← Tuần trước
          </button>
          <button type="button" className="btn btn--ghost" onClick={onToday}>
            Tuần này
          </button>
          <button type="button" className="btn btn--ghost" onClick={() => onShift(1)}>
            Tuần sau →
          </button>
        </div>
        <span className="mono" style={{ fontSize: '0.875rem', color: 'var(--ink-soft)' }}>
          {dateOf(weekStart.toISOString())} – {dateOf(weekEnd.toISOString())}
        </span>
      </div>

      <div className="row" style={{ marginTop: 'var(--gap-4)', gap: 'var(--gap-4)' }}>
        <label style={{ flex: '1 1 16rem', maxWidth: '24rem' }}>
          <span className="field__label">Lọc theo môn học</span>
          <select
            className="field__input"
            value={courseId}
            onChange={(e) => onCourseChange(e.target.value)}
          >
            <option value="">Tất cả môn</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} — {c.name}
              </option>
            ))}
          </select>
        </label>

        <label className="row" style={{ gap: '0.4rem', paddingTop: '1.2rem' }}>
          <input
            type="checkbox"
            checked={showExams}
            onChange={(e) => onToggleExams(e.target.checked)}
          />
          <span style={{ fontSize: '0.875rem' }}>Hiện cả lịch thi</span>
        </label>
      </div>
    </div>
  );
}
