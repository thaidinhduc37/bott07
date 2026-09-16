import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '@/services/api';
import { dateOf, isoDate, mondayOf, scheduleApi, type CourseRef, type Timetable } from '@/services/schedule-api';
import { TimetableWeek } from '@/components/schedule/TimetableWeek';
import { Icon } from '@/components/shared/Icon';

export default function StudentSchedulePage() {
  const [weekStart, setWeekStart] = useState<Date>(() => mondayOf(new Date()));
  const [courseId, setCourseId] = useState('');
  const [showExams, setShowExams] = useState(true);
  const [courses, setCourses] = useState<CourseRef[]>([]);
  const [data, setData] = useState<Timetable | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void scheduleApi.myCourses().then((r) => setCourses(r.items)).catch(() => setCourses([]));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const end = new Date(weekStart);
    end.setDate(weekStart.getDate() + 6);
    try {
      setData(
        await scheduleApi.mine({
          from: isoDate(weekStart),
          to: isoDate(end),
          courseId: courseId || undefined,
        }),
      );
    } catch (e) {
      setData(null);
      setError(
        e instanceof ApiError
          ? e.message
          : 'Không tải được thời khóa biểu. Kiểm tra kết nối tới máy chủ.',
      );
    } finally {
      setLoading(false);
    }
  }, [weekStart, courseId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Lật theo tuần ĐANG XEM, không phải nhảy cố định về 3 tuần quanh hôm nay —
  // bấm "Tuần tới" liên tiếp phải đi tiếp mãi, không dừng lại sau một lần.
  function shiftWeek(deltaWeeks: number) {
    const next = new Date(weekStart);
    next.setDate(weekStart.getDate() + deltaWeeks * 7);
    setWeekStart(next);
  }
  const isCurrentWeek = isoDate(weekStart) === isoDate(mondayOf(new Date()));

  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekStart.getDate() + 6);

  const sessions = data?.sessions ?? [];
  const exams = showExams ? (data?.exams ?? []) : [];

  return (
    <div className="stack shell--full">
      <header>
        <span className="eyebrow">Học vụ</span>
        <h1 className="display page-title">
          Lịch học và lịch thi
        </h1>
        {data?.class && (
          <p style={{ color: 'var(--ink-soft)', margin: '0.35rem 0 0' }}>
            Lớp {data.class.code} — {data.class.name}
          </p>
        )}
      </header>

      {/* ------------------------------------------------------ điều hướng tuần */}
      <div className="sheet" style={{ padding: '0.6rem 0.75rem' }}>
        <div className="row" style={{ flexWrap: 'wrap', gap: 'var(--gap-3)', justifyContent: 'space-between' }}>
          <div className="row" style={{ gap: 'var(--gap-3)', flexWrap: 'wrap' }}>
            <div className="seg">
              <button type="button" className="seg__opt" onClick={() => shiftWeek(-1)}>
                Tuần trước
              </button>
              <button
                type="button"
                className={`seg__opt${isCurrentWeek ? ' seg__opt--on' : ''}`}
                onClick={() => setWeekStart(mondayOf(new Date()))}
              >
                Tuần này
              </button>
              <button type="button" className="seg__opt" onClick={() => shiftWeek(1)}>
                Tuần tới
              </button>
            </div>
            <span className="row" style={{ gap: '0.4rem', fontSize: '0.9375rem', color: 'var(--ink-soft)' }}>
              <Icon name="calendar" size={18} />
              <span className="mono">
                {dateOf(weekStart.toISOString())} – {dateOf(weekEnd.toISOString())}
              </span>
            </span>
          </div>

          <div className="row" style={{ gap: 'var(--gap-3)', flexWrap: 'wrap' }}>
            <select
              className="field__input"
              style={{
                width: 'auto', flex: '0 1 auto', minWidth: '11rem', minHeight: '2.1rem',
                padding: '0.3rem 2rem 0.3rem 0.7rem', fontSize: '0.8125rem',
              }}
              value={courseId}
              onChange={(e) => setCourseId(e.target.value)}
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
                <input
                  type="checkbox"
                  checked={showExams}
                  onChange={(e) => setShowExams(e.target.checked)}
                />
                <span className="switch__track" aria-hidden="true">
                  <span className="switch__thumb" />
                </span>
              </span>
              <span style={{ fontSize: '0.8125rem' }}>Hiện cả lịch thi</span>
            </label>
          </div>
        </div>
      </div>

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <p className="eyebrow">Đang tải…</p>
      ) : (
        data && (
          <>
            <TimetableWeek
              sessions={sessions}
              exams={exams}
              from={data.range.from}
              to={data.range.to}
            />
            <p style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', margin: 0 }}>
              Giờ hiển thị theo múi giờ Việt Nam ({data.range.timezone}).
              {' '}
              {sessions.length} buổi học
              {exams.length > 0 && `, ${exams.length} ca thi`}
              {' '}trong tuần.
            </p>
          </>
        )
      )}
    </div>
  );
}
