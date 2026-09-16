import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '@/services/api';
import {
  isoDate,
  mondayOf,
  scheduleApi,
  type CourseRef,
  type Timetable,
} from '@/services/schedule-api';

export function useStudentSchedule() {
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

  function shiftWeek(delta: number) {
    setWeekStart((prev) => {
      const next = new Date(prev);
      next.setDate(prev.getDate() + delta * 7);
      return next;
    });
  }

  function goToday() {
    setWeekStart(mondayOf(new Date()));
  }

  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekStart.getDate() + 6);

  return {
    weekStart,
    weekEnd,
    courseId,
    setCourseId,
    showExams,
    setShowExams,
    courses,
    data,
    loading,
    error,
    shiftWeek,
    goToday,
  };
}
