import { fmtDay, timeOf, weekdayOf, type ExamTermItem } from '@/services/schedule-api';
import { Metrics } from '@/components/shared/Metrics';

/**
 * Tab "Lịch thi": bảng các kỳ thi học viên phải thi trong học kỳ đang chọn.
 *
 * Trên màn rộng là bảng `.data-table`; dưới 40rem mỗi kỳ thi thành một thẻ
 * (`.term-exam-card`) để không phải cuộn ngang ở 400px. Kỳ thi đã qua làm
 * nhạt chữ, kỳ sắp tới giữ đậm.
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

      <div className="term-exam-grid">
        {/* ---------------------------------------------------------- bảng (màn rộng) */}
        <div className="table-wrap term-exam-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">STT</th>
                <th scope="col">Môn học</th>
                <th scope="col">Ngày thi</th>
                <th scope="col">Ca thi</th>
                <th scope="col">Phòng thi</th>
                <th scope="col">Hình thức</th>
                <th scope="col">Được mang vào</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => (
                <tr
                  key={it.id}
                  className={it.upcoming ? '' : 'term-exam-row--past'}
                  onClick={onSelect ? () => onSelect(it) : undefined}
                >
                  <td className="num">{i + 1}</td>
                  <td>
                    <ExamCourse it={it} />
                  </td>
                  <td>
                    <ExamDate it={it} />
                  </td>
                  <td>{it.shift ?? '—'}</td>
                  <td>
                    <ExamRoom it={it} />
                  </td>
                  <td>{it.formatLabel ?? '—'}</td>
                  <td>{it.allowedMaterials ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* ---------------------------------------------------------- thẻ (màn hẹp) */}
        <div className="term-exam-cards">
          {items.map((it) => (
            <article
              key={it.id}
              className={`term-exam-card${it.upcoming ? '' : ' term-exam-card--past'}`}
              onClick={onSelect ? () => onSelect(it) : undefined}
            >
              <div className="term-exam-card__head">
                <ExamCourse it={it} />
              </div>
              <div className="term-exam-card__row">
                <span className="term-exam-card__label">Ngày thi</span>
                <ExamDate it={it} />
              </div>
              <div className="term-exam-card__row">
                <span className="term-exam-card__label">Ca thi</span>
                <span>{it.shift ?? '—'}</span>
              </div>
              <div className="term-exam-card__row">
                <span className="term-exam-card__label">Phòng thi</span>
                <ExamRoom it={it} />
              </div>
              <div className="term-exam-card__row">
                <span className="term-exam-card__label">Hình thức</span>
                <span>{it.formatLabel ?? '—'}</span>
              </div>
              <div className="term-exam-card__row">
                <span className="term-exam-card__label">Được mang vào</span>
                <span>{it.allowedMaterials ?? '—'}</span>
              </div>
            </article>
          ))}
        </div>
      </div>
    </>
  );
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
