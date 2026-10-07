import { fmtDay, timeOf, weekdayOf, type ExamTermItem } from '@/services/schedule-api';
import { Metrics } from '@/components/shared/Metrics';

/**
 * Tab "Lịch thi": các kỳ thi học viên phải thi trong học kỳ đang chọn.
 *
 * Mỗi kỳ thi là một thẻ (`.term-exam-card`) trong lưới tự co theo bề rộng. Kỳ thi đã qua làm nhạt chữ,
 * kỳ sắp tới giữ đậm và có nhãn số ngày còn lại.
 */
export function ExamTable({
  examCount,
  upcomingCount,
  totalCredits,
  items,
  onSelect,
}: {
  examCount: number;
  upcomingCount: number;
  totalCredits: number;
  items: ExamTermItem[];
  onSelect?: (item: ExamTermItem) => void;
}) {
  return (
    <>
      <Metrics
        label="Số liệu lịch thi"
        items={[
          { label: 'Số môn thi', value: examCount },
          { label: 'Sắp thi', value: upcomingCount, hint: 'chưa tới ngày thi' },
          { label: 'Tín chỉ các môn thi', value: totalCredits },
        ]}
      />

      <div className="term-exam-cards">
        {items.map((it) => {
          const left = daysUntil(it.examDate);
          return (
            <article
              key={it.id}
              className={`term-exam-card${it.upcoming ? '' : ' term-exam-card--past'}`}
              onClick={onSelect ? () => onSelect(it) : undefined}
            >
              <div className="term-exam-card__head">
                <ExamCourse it={it} />
                <span className={`tag ${it.upcoming ? 'tag--pen' : 'tag--muted'}`}>
                  {it.upcoming ? (left <= 0 ? 'Hôm nay' : `Còn ${left} ngày`) : 'Đã thi'}
                </span>
              </div>
              <div className="term-exam-card__row">
                <span className="term-exam-card__label">Ngày thi</span>
                <ExamDate it={it} />
              </div>
              <div className="term-exam-card__cols">
                <div className="term-exam-card__row">
                  <span className="term-exam-card__label">Ca thi</span>
                  <span>{it.shift ?? '—'}</span>
                </div>
                <div className="term-exam-card__row">
                  <span className="term-exam-card__label">Hình thức</span>
                  <span>{it.formatLabel ?? '—'}</span>
                </div>
              </div>
              <div className="term-exam-card__row">
                <span className="term-exam-card__label">Phòng thi</span>
                <ExamRoom it={it} />
              </div>
              <div className="term-exam-card__row">
                <span className="term-exam-card__label">Được mang vào</span>
                <span>{it.allowedMaterials ?? '—'}</span>
              </div>
            </article>
          );
        })}
      </div>
    </>
  );
}

/** Số ngày từ hôm nay tới ngày thi ("YYYY-MM-DD"), tính theo giờ địa phương. */
function daysUntil(iso: string): number {
  const [y, m, d] = iso.split('-').map(Number);
  const target = new Date(y, m - 1, d).getTime();
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  return Math.round((target - today) / 86400000);
}

/** Mã môn (mono) + tên trên dòng 1, giảng viên trên dòng 2 nhạt. */
function ExamCourse({ it }: { it: ExamTermItem }) {
  return (
    <div className="term-course">
      <span className="term-course__name">
        <span className="mono">{it.course?.code ?? '—'}</span>
        <span>{it.course?.name ?? 'Chưa rõ môn'}</span>
      </span>
      <span className="term-course__lec">{it.lecturer ? it.lecturer.name : 'Chưa có giảng viên'}</span>
    </div>
  );
}

/** Ngày thi (đậm) + dòng nhạt "Thứ · giờ bắt đầu · thời lượng". */
function ExamDate({ it }: { it: ExamTermItem }) {
  return (
    <div className="term-range">
      <span className="term-range__dates">
        <strong>{fmtDay(it.examDate)}</strong>
      </span>
      <span className="term-range__count">
        {weekdayOf(it.startsAt)} · {timeOf(it.startsAt)} · {it.durationMinutes} phút
      </span>
    </div>
  );
}

/** Phòng thi + tòa nhà, hoặc "Chưa xếp phòng" khi phòng rỗng. */
function ExamRoom({ it }: { it: ExamTermItem }) {
  if (!it.room) return <span className="term-dim">Chưa xếp phòng</span>;
  return (
    <span>
      {it.room}
      {it.building ? ` · ${it.building}` : ''}
    </span>
  );
}
