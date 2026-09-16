import {
  dateOf,
  dayKey,
  timeOf,
  weekdayOf,
  type Exam,
  type Session,
} from '@/services/schedule-api';
import { Icon } from '@/components/shared/Icon';

type Entry = Session | Exam;

const WEEKDAY_SHORT = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'CN'];
const HOUR_PX = 60;
/** Giờ sớm/muộn nhất luôn hiện trên lưới, kể cả khi tuần đó trống — một
 * tuần thiếu tiết đầu/cuối không nên co lưới lại trông như dữ liệu lỗi. */
const DEFAULT_START_HOUR = 7;
const DEFAULT_END_HOUR = 21;

function minutesOfDay(iso: string): number {
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes();
}

/**
 * Thời khóa biểu dạng lưới giờ × ngày, theo đúng mẫu tham chiếu: cột giờ bên
 * trái, 7 cột ngày, mỗi buổi học/ca thi là một khối màu đặt đúng vị trí theo
 * giờ thực — không còn danh sách xếp dọc theo ngày.
 */
export function TimetableWeek({
  sessions,
  exams,
  from,
  to,
}: {
  sessions: Session[];
  exams: Exam[];
  from: string;
  to: string;
}) {
  const entries: Entry[] = [...sessions, ...exams];

  // Dựng đủ 7 ngày kể cả ngày trống.
  const days: string[] = [];
  const cursor = new Date(from);
  const end = new Date(to);
  while (cursor <= end && days.length < 7) {
    days.push(
      new Intl.DateTimeFormat('en-CA', {
        year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'Asia/Ho_Chi_Minh',
      }).format(cursor),
    );
    cursor.setDate(cursor.getDate() + 1);
  }

  const today = new Intl.DateTimeFormat('en-CA', {
    year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'Asia/Ho_Chi_Minh',
  }).format(new Date());

  const byDay = new Map<string, Entry[]>();
  for (const e of entries) {
    const k = dayKey(e.startsAt);
    if (!byDay.has(k)) byDay.set(k, []);
    byDay.get(k)!.push(e);
  }

  let startHour = DEFAULT_START_HOUR;
  let endHour = DEFAULT_END_HOUR;
  for (const e of entries) {
    startHour = Math.min(startHour, Math.floor(minutesOfDay(e.startsAt) / 60));
    endHour = Math.max(endHour, Math.ceil(minutesOfDay(e.endsAt) / 60));
  }
  const totalHours = endHour - startHour;
  const bodyHeight = totalHours * HOUR_PX;

  const hourMarks = Array.from({ length: totalHours + 1 }, (_, i) => startHour + i);

  return (
    <div className="sheet timetable-scroll">
      <div className="timetable-grid" style={{ minWidth: '52rem' }}>
        {/* --------------------------------------------------------- header */}
        <div className="timetable-grid__row-labels" />
        {days.map((d, i) => {
          const isToday = d === today;
          return (
            <div
              key={d}
              className={`timetable-grid__day-head${isToday ? ' timetable-grid__day-head--today' : ''}`}
            >
              <div className="timetable-grid__weekday">{WEEKDAY_SHORT[i]}</div>
              <div className="mono timetable-grid__date">{dateOf(`${d}T12:00:00+07:00`)}</div>
            </div>
          );
        })}

        {/* ----------------------------------------------------------- body */}
        <div className="timetable-grid__hours" style={{ height: bodyHeight }}>
          {hourMarks.map((h) => (
            <div
              key={h}
              className="timetable-grid__hour-label"
              style={{ top: (h - startHour) * HOUR_PX + 2 }}
            >
              {String(h).padStart(2, '0')}:00
            </div>
          ))}
        </div>

        {days.map((d) => {
          const items = byDay.get(d) ?? [];
          const isToday = d === today;
          return (
            <div
              key={d}
              className={`timetable-grid__day-col${isToday ? ' timetable-grid__day-col--today' : ''}`}
              style={{ height: bodyHeight }}
            >
              {hourMarks.slice(0, -1).map((h) => (
                <div key={h} className="timetable-grid__gridline" style={{ top: (h - startHour) * HOUR_PX }} />
              ))}
              {items.map((e) => (
                <EntryBlock key={`${e.kind}-${e.id}`} entry={e} startHour={startHour} />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Một khối buổi học/ca thi, đặt tuyệt đối theo giờ thực trong cột ngày của nó.
 * Nẹp trái theo loại — mực = lý thuyết, hổ phách = thực hành/lab, đỏ = thi.
 */
function EntryBlock({ entry, startHour }: { entry: Entry; startHour: number }) {
  const isExam = entry.kind === 'EXAM';
  const cancelled = entry.status === 'CANCELLED' || entry.status === 'HOLIDAY';
  const isLab = !isExam && (entry as Session).sessionType !== 'LY_THUYET';
  const variant = isExam ? 'timetable-block--exam' : isLab ? 'timetable-block--lab' : '';

  const top = minutesOfDay(entry.startsAt) - startHour * 60;
  const height = minutesOfDay(entry.endsAt) - minutesOfDay(entry.startsAt);

  return (
    <div
      className={`timetable-block ${variant}${cancelled ? ' timetable-block--off' : ''}`.trim()}
      style={{ top: (top / 60) * HOUR_PX, height: Math.max((height / 60) * HOUR_PX, 34) }}
      title={`${entry.course.name} · ${timeOf(entry.startsAt)}–${timeOf(entry.endsAt)}`}
    >
      <div className="timetable-block__top">
        {isExam && (
          <span className="tag tag--seal timetable-block__flag">
            <Icon name="bell" size={12} /> lịch thi
          </span>
        )}
        {!isExam && isLab && <span className="tag tag--warn timetable-block__flag">thực hành</span>}
        <span className="timetable-block__time">
          {timeOf(entry.startsAt)}–{timeOf(entry.endsAt)}
        </span>
      </div>
      <h4 className="timetable-block__title">{entry.course.name}</h4>
      <div className="timetable-block__meta">
        <span className="timetable-block__meta-item">
          <Icon name="location" size={13} />
          {entry.room}
          {entry.building && ` · ${entry.building}`}
        </span>
        {isExam && (
          <span className="timetable-block__meta-item">{(entry as Exam).formatLabel}</span>
        )}
      </div>
      {cancelled && <span className="tag tag--warn" style={{ marginTop: '0.25rem' }}>{(entry as Session).statusLabel ?? 'đã hủy'}</span>}
    </div>
  );
}
