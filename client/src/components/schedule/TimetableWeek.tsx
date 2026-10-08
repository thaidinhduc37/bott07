import {
  dateOf,
  dayKey,
  timeOf,
  weekdayOf,
  type Exam,
  type ScheduleEntry,
  type Session,
} from '@/services/schedule-api';
import { Icon } from '@/components/shared/Icon';

type Entry = ScheduleEntry;

const WEEKDAY_SHORT = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'CN'];
const HOUR_PX = 60;
/** Giờ sớm/muộn nhất luôn hiện trên lưới, kể cả khi tuần đó trống — một
 * tuần thiếu tiết đầu/cuối không nên co lưới lại trông như dữ liệu lỗi. */
const DEFAULT_START_HOUR = 7;
const DEFAULT_END_HOUR = 21;

/** Vị trí ngang của một khối: làn thứ `lane` trong `lanes` làn của cụm chồng giờ. */
interface Lane {
  lane: number;
  lanes: number;
}

/**
 * Xếp làn cho các mục trong MỘT ngày để mục trùng giờ nằm cạnh nhau thay vì đè lên nhau: gom các mục chồng giờ bắc cầu thành cụm,
 * mỗi mục nhận làn đầu tiên còn trống, bề rộng chia đều theo số làn của cụm (mục không trùng ai vẫn chiếm trọn cột).
 */
function layoutLanes(items: Entry[]): Map<string, Lane> {
  const sorted = [...items].sort(
    (a, b) => +new Date(a.startsAt) - +new Date(b.startsAt) || +new Date(b.endsAt) - +new Date(a.endsAt),
  );
  const result = new Map<string, Lane>();
  let cluster: { key: string; lane: number }[] = [];
  let laneEnds: number[] = [];
  let clusterEnd = -Infinity;

  const flush = () => {
    for (const c of cluster) result.set(c.key, { lane: c.lane, lanes: laneEnds.length });
    cluster = [];
    laneEnds = [];
  };

  for (const e of sorted) {
    const start = +new Date(e.startsAt);
    const end = +new Date(e.endsAt);
    if (start >= clusterEnd) flush();
    let lane = laneEnds.findIndex((laneEnd) => laneEnd <= start);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(end);
    } else {
      laneEnds[lane] = end;
    }
    cluster.push({ key: `${e.kind}-${e.id}`, lane });
    clusterEnd = Math.max(clusterEnd, end);
  }
  flush();
  return result;
}

function minutesOfDay(iso: string): number {
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes();
}

/**
 * Thời khóa biểu lưới giờ × ngày: cột giờ bên trái, 7 cột ngày, mỗi buổi học hoặc ca thi là một khối đặt đúng vị trí theo giờ thực.
 * Có `onSelect` thì mỗi khối là nút bấm mở chi tiết; `selectedKey` (`${kind}-${id}`) đánh dấu khối đang mở.
 */
export function TimetableWeek({
  sessions,
  exams,
  from,
  to,
  onSelect,
  selectedKey,
}: {
  sessions: Session[];
  exams: Exam[];
  from: string;
  to: string;
  onSelect?: (entry: ScheduleEntry) => void;
  selectedKey?: string;
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

  const lanesByDay = new Map<string, Map<string, Lane>>();
  for (const [day, dayItems] of byDay) lanesByDay.set(day, layoutLanes(dayItems));

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
                <EntryBlock
                  key={`${e.kind}-${e.id}`}
                  entry={e}
                  startHour={startHour}
                  lane={lanesByDay.get(d)?.get(`${e.kind}-${e.id}`)}
                  onSelect={onSelect}
                  selected={selectedKey === `${e.kind}-${e.id}`}
                />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Nhãn + màu tag cho loại buổi học. LY_THUYET không gắn tag. */
function sessionTag(e: Session): { label: string; cls: string } | null {
  switch (e.sessionType) {
    case 'THUC_HANH':
      return { label: e.sessionTypeLabel, cls: 'tag--warn' };
    case 'KIEM_TRA_GIUA_KY':
      return { label: e.sessionTypeLabel, cls: 'tag--seal' };
    case 'ON_TAP':
    case 'HOC_BU':
      return { label: e.sessionTypeLabel, cls: 'tag--muted' };
    default:
      return null;
  }
}

/** Một khối buổi học hoặc ca thi đặt tuyệt đối theo giờ thực. Nẹp trái theo loại: mực = lý thuyết, hổ phách = thực hành, đỏ = thi. */
function EntryBlock({
  entry,
  startHour,
  lane,
  onSelect,
  selected,
}: {
  entry: Entry;
  startHour: number;
  lane?: Lane;
  onSelect?: (entry: ScheduleEntry) => void;
  selected?: boolean;
}) {
  const isExam = entry.kind === 'EXAM';
  const cancelled = entry.status === 'CANCELLED' || entry.status === 'HOLIDAY';
  const isLab = !isExam && (entry as Session).sessionType === 'THUC_HANH';
  const variant = isExam ? 'timetable-block--exam' : isLab ? 'timetable-block--lab' : '';
  const tag = isExam ? null : sessionTag(entry as Session);
  const hasNote = Boolean(entry.lecturerNote);

  const top = minutesOfDay(entry.startsAt) - startHour * 60;
  const height = minutesOfDay(entry.endsAt) - minutesOfDay(entry.startsAt);
  const lanes = lane?.lanes ?? 1;
  const position: React.CSSProperties = {
    top: (top / 60) * HOUR_PX,
    height: Math.max((height / 60) * HOUR_PX, 34),
    // Chia cột theo làn; chừa khe 2px mỗi bên giữa các khối cạnh nhau.
    ...(lanes > 1 && {
      left: `calc(${((lane?.lane ?? 0) / lanes) * 100}% + 2px)`,
      right: 'auto',
      width: `calc(${100 / lanes}% - 4px)`,
    }),
  };

  const ariaLabel = [
    `${entry.course.code} ${entry.course.name}`,
    `${weekdayOf(entry.startsAt)} ${timeOf(entry.startsAt)}–${timeOf(entry.endsAt)}`,
    `phòng ${entry.room}`,
    hasNote ? 'có yêu cầu của giảng viên' : '',
  ]
    .filter(Boolean)
    .join(', ');

  const title = [
    `${entry.course.name} · ${timeOf(entry.startsAt)}–${timeOf(entry.endsAt)}`,
    !isExam && entry.class ? `Lớp ${entry.class.code}` : '',
  ]
    .filter(Boolean)
    .join(' · ');

  const past = new Date(entry.endsAt).getTime() < Date.now();
  const cls = `timetable-block ${variant}${cancelled ? ' timetable-block--off' : ''}${past ? ' timetable-block--past' : ''}${
    onSelect ? ' timetable-block--click' : ''
  }${selected ? ' timetable-block--selected' : ''}`.trim();

  const body = (
    <>
      <div className="timetable-block__top">
        {isExam && (
          <span className="tag tag--seal timetable-block__flag">
            <Icon name="bell" size={12} /> lịch thi
          </span>
        )}
        {!isExam && tag && (
          <span className={`tag ${tag.cls} timetable-block__flag`}>{tag.label}</span>
        )}
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
        {hasNote && (
          <span className="timetable-block__note" title="Có yêu cầu của giảng viên">
            <Icon name="pencil" size={12} />
            <span className="sr-only">có yêu cầu của giảng viên</span>
          </span>
        )}
      </div>
      {cancelled && (
        <span className="tag tag--warn" style={{ marginTop: '0.25rem' }}>
          {isExam ? 'đã hủy' : (entry as Session).statusLabel ?? 'đã hủy'}
        </span>
      )}
    </>
  );

  if (!onSelect) {
    return (
      <div
        className={cls}
        style={position}
        title={title}
      >
        {body}
      </div>
    );
  }

  return (
    <button
      type="button"
      className={cls}
      style={position}
      title={title}
      aria-label={ariaLabel}
      aria-pressed={selected}
      onClick={() => onSelect(entry)}
    >
      {body}
    </button>
  );
}
