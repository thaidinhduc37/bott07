import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { dayLabel, hhmm, todayIso } from '@/components/study/format';
import { formsApi, type SubmissionSummary } from '@/services/forms-api';
import { learningApi, type ExamPlanItem } from '@/services/learning-api';
import { scheduleApi, type Timetable } from '@/services/schedule-api';

/**
 * Cột ngữ cảnh bên phải trang Hỏi đáp của học viên: lịch học hôm nay, kỳ thi gần nhất, đơn gần đây.
 * Mỗi nguồn tải độc lập; nguồn nào lỗi thì chỉ thẻ đó bị bỏ, không ảnh hưởng việc hỏi đáp.
 */
export function ChatContextRail() {
  const [today, setToday] = useState<Timetable | null>(null);
  const [exam, setExam] = useState<ExamPlanItem | null>(null);
  const [subs, setSubs] = useState<SubmissionSummary[] | null>(null);

  useEffect(() => {
    const day = todayIso();
    void scheduleApi
      .mine({ from: day, to: day })
      .then(setToday)
      .catch(() => setToday(null));
    void learningApi
      .examPlan()
      .then((r) => setExam(r.exams[0] ?? null))
      .catch(() => setExam(null));
    void formsApi
      .list()
      .then((r) => setSubs(r.items.slice(0, 3)))
      .catch(() => setSubs([]));
  }, []);

  const entries = today
    ? [
        ...today.sessions.map((s) => ({
          key: s.id,
          at: s.startsAt,
          end: s.endsAt,
          title: s.course.name,
          place: s.room,
        })),
        ...today.exams.map((e) => ({
          key: e.id,
          at: e.startsAt,
          end: e.endsAt,
          title: `Thi: ${e.course.name}`,
          place: e.room,
        })),
      ].sort((a, b) => a.at.localeCompare(b.at))
    : [];

  return (
    <aside className="chat-rail" aria-label="Thông tin nhanh">
      <section className="chat-rail__card">
        <h2 className="chat-rail__h">Lịch học hôm nay</h2>
        {today === null ? (
          <p className="chat-rail__empty">Chưa có dữ liệu lịch.</p>
        ) : entries.length === 0 ? (
          <p className="chat-rail__empty">Hôm nay không có buổi học hay ca thi.</p>
        ) : (
          <ol className="chat-rail__list">
            {entries.map((e) => (
              <li key={e.key} className="chat-rail__item">
                <span className="chat-rail__time">
                  {hhmm(e.at)}–{hhmm(e.end)}
                </span>
                <span className="chat-rail__main">
                  <span className="chat-rail__title">{e.title}</span>
                  <span className="chat-rail__meta">{e.place || 'Chưa xếp phòng'}</span>
                </span>
              </li>
            ))}
          </ol>
        )}
        <Link to="/sinh-vien/lich" className="chat-rail__link">
          Xem lịch tuần
        </Link>
      </section>

      {exam && (
        <section className="chat-rail__card">
          <h2 className="chat-rail__h">Kỳ thi gần nhất</h2>
          <p className="chat-rail__title">
            <span className="mono">{exam.course.code}</span> — {exam.course.name}
          </p>
          <p className="chat-rail__meta">
            {dayLabel(exam.examDate)} · {exam.daysLeft === 0 ? 'hôm nay' : `còn ${exam.daysLeft} ngày`}
          </p>
          <Link to={`/sinh-vien/on-tap?tab=ke-hoach#${exam.id}`} className="chat-rail__link">
            Kế hoạch ôn thi
          </Link>
        </section>
      )}

      {subs && subs.length > 0 && (
        <section className="chat-rail__card">
          <h2 className="chat-rail__h">Đơn gần đây</h2>
          <ul className="chat-rail__list">
            {subs.map((s) => (
              <li key={s.id} className="chat-rail__item chat-rail__item--stack">
                <span className="chat-rail__title">{s.template.name}</span>
                <span className="chat-rail__meta">
                  <span className="mono">{s.code}</span> · {s.statusLabel}
                </span>
              </li>
            ))}
          </ul>
          <Link to="/sinh-vien/bieu-mau" className="chat-rail__link">
            Tất cả đơn
          </Link>
        </section>
      )}
    </aside>
  );
}
