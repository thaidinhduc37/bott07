import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ApiError } from '@/services/api';
import {
  isoDate,
  mondayOf,
  scheduleApi,
  type CourseRef,
  type ScheduleEntry,
  type Timetable,
} from '@/services/schedule-api';
import { TimetableWeek } from '@/components/schedule/TimetableWeek';
import { EntryDetail } from '@/components/schedule/EntryDetail';
import { PageHeader } from '@/components/shared/PageHeader';
import { TabPanel, Tabs } from '@/components/shared/Tabs';
import { ExamTermPanel } from '@/components/schedule/ExamTermPanel';
import { WeekToolbar } from '@/components/schedule/WeekToolbar';

export default function StudentSchedulePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [weekStart, setWeekStart] = useState<Date>(() => mondayOf(new Date()));
  const [courseId, setCourseId] = useState('');
  const [showExams, setShowExams] = useState(true);
  const [courses, setCourses] = useState<CourseRef[]>([]);
  const [data, setData] = useState<Timetable | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ScheduleEntry | null>(null);

  // Liên kết sâu từ thông báo: ?ngay=YYYY-MM-DD&buoi=SESSION-<id>|EXAM-<id>.
  // Nhảy tới tuần chứa ngày đó; tự mở chi tiết sau khi dữ liệu tải xong.
  const deepLinkRef = useRef<{ day: string; entryKey: string } | null>(null);
  const [searchParamsInit] = useState(() => {
    const day = searchParams.get('ngay');
    const entryKey = searchParams.get('buoi');
    if (!day || !entryKey) return null;
    return { day, entryKey };
  });
  useEffect(() => {
    const dl = deepLinkRef.current ?? searchParamsInit;
    deepLinkRef.current = dl;
    if (!dl) return;
    const d = new Date(`${dl.day}T12:00:00+07:00`);
    if (!Number.isNaN(d.getTime())) setWeekStart(mondayOf(d));
  }, [searchParamsInit]);

  // Dữ liệu về: mở chi tiết của mục liên kết (nếu tuần hiện có nó) rồi xóa
  // `buoi` khỏi URL — mở lại chi tiết bằng cách bấm khối, không phải URL.
  useEffect(() => {
    const dl = deepLinkRef.current;
    if (!dl || loading || !data) return;
    const all = [...data.sessions, ...data.exams];
    const found = all.find((e) => `${e.kind}-${e.id}` === dl.entryKey);
    if (found) setSelected(found);
    deepLinkRef.current = null;
    if (searchParams.has('buoi')) {
      const next = new URLSearchParams(searchParams);
      next.delete('buoi');
      setSearchParams(next, { replace: true });
    }
  }, [loading, data, searchParams, setSearchParams]);

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

  // Hai tab: "Lịch học" (cách xem theo tuần như cũ) và "Lịch thi" (bảng kỳ thi theo học kỳ).
  type Tab = 'lich-hoc' | 'lich-thi';
  const tab: Tab = searchParams.get('tab') === 'lich-thi' ? 'lich-thi' : 'lich-hoc';
  function changeTab(next: Tab) {
    const p = new URLSearchParams(searchParams);
    p.set('tab', next);
    setSearchParams(p, { replace: true });
  }

  const sessions = data?.sessions ?? [];
  const exams = showExams ? (data?.exams ?? []) : [];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Học vụ"
        title="Lịch học và lịch thi"
        description={data?.class ? data.class.name : undefined}
        tabs={
          <Tabs
            label="Nội dung trang Lịch"
            idPrefix="lich-hv"
            value={tab}
            onChange={changeTab}
            items={[
              { id: 'lich-hoc', label: 'Lịch học' },
              { id: 'lich-thi', label: 'Lịch thi' },
            ]}
          />
        }
      />

      <TabPanel idPrefix="lich-hv" tab={tab}>
      {tab === 'lich-thi' ? (
        <ExamTermPanel />
      ) : (
      <div className="stack">

      <WeekToolbar
        weekStart={weekStart}
        isCurrentWeek={isCurrentWeek}
        onShift={shiftWeek}
        onToday={() => setWeekStart(mondayOf(new Date()))}
        courses={courses}
        courseId={courseId}
        onCourse={setCourseId}
        showExams={showExams}
        onShowExams={setShowExams}
      />

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
              onSelect={(e) => setSelected(e)}
              selectedKey={selected ? `${selected.kind}-${selected.id}` : undefined}
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
      )}
      </TabPanel>

      {selected && (
        <EntryDetail entry={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
