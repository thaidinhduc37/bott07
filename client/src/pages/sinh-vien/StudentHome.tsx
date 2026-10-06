import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Icon } from '@/components/shared/Icon';
import { useSession } from '@/components/shared/SessionProvider';
import { ActivityBars } from '@/components/study/ActivityBars';
import { viScore } from '@/components/study/format';
import { learningApi, type ExamPlanItem, type ProgressOverview } from '@/services/learning-api';
import { scheduleApi, type Timetable } from '@/services/schedule-api';

const WEEKDAY = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'];

/** "T2, 07/12" từ "2026-12-07" — đọc theo giờ địa phương, không lệch ngày do UTC. */
function examDay(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  return `${WEEKDAY[new Date(y, m - 1, d).getDay()]}, ${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}`;
}

const hhmm = (iso: string) =>
  new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(iso));

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

const todayLabel = () =>
  new Intl.DateTimeFormat('vi-VN', { weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric' }).format(
    new Date(),
  );

interface Kpi {
  label: string;
  value: string | number;
  hint: ReactNode;
  to?: string;
  tone?: 'warn' | 'ok';
}

/** Điểm (thang 10) → màu thanh: từ 8 là tốt, dưới 5 cần chú ý. */
const scoreTone = (s: number | null) =>
  s === null ? '' : s >= 8 ? ' prog__fill--ok' : s < 5 ? ' prog__fill--warn' : '';

export default function StudentHome() {
  const { user } = useSession();
  const profile = user?.studentProfile;
  // Mỗi nguồn số liệu tải độc lập; lỗi API thì bỏ riêng mục đó, không làm trắng cả trang.
  const [progress, setProgress] = useState<ProgressOverview | null>(null);
  const [nextExam, setNextExam] = useState<ExamPlanItem | null>(null);
  const [today, setToday] = useState<Timetable | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const day = todayIso();
    void Promise.allSettled([
      learningApi.progress().then(setProgress),
      learningApi.examPlan().then((r) => setNextExam(r.exams[0] ?? null)),
      scheduleApi.mine({ from: day, to: day }).then(setToday),
    ]).then(() => setLoaded(true));
  }, []);

  const due = progress?.review.due ?? 0;
  const metrics: Kpi[] = progress
    ? [
        {
          label: 'Chuỗi ngày ôn',
          value: `${progress.streakDays} ngày`,
          hint: progress.streakDays > 0 ? 'liên tiếp' : 'Làm một đề để bắt đầu',
        },
        {
          label: '7 ngày qua',
          value: `${progress.week.sessions} lượt`,
          hint: progress.week.avgScore !== null ? `điểm TB ${viScore(progress.week.avgScore)}` : 'chưa có điểm',
        },
        {
          label: 'Câu sai đến hạn',
          value: due,
          hint: due > 0 ? 'Ôn ngay' : 'Không có câu nào',
          to: '/sinh-vien/on-tap/so-cau-sai',
          tone: due > 0 ? 'warn' : undefined,
        },
        nextExam
          ? {
              label: 'Kỳ thi gần nhất',
              value: nextExam.daysLeft === 0 ? 'Hôm nay' : `${nextExam.daysLeft} ngày`,
              hint: (
                <>
                  <span className="mono">{nextExam.course.code}</span> · {examDay(nextExam.examDate)}
                </>
              ),
              to: `/sinh-vien/on-tap?tab=ke-hoach#${nextExam.id}`,
            }
          : { label: 'Kỳ thi gần nhất', value: '—', hint: 'Chưa có lịch thi' },
      ]
    : [];

  const entries = today
    ? [
        ...today.sessions.map((s) => ({
          key: s.id,
          at: s.startsAt,
          end: s.endsAt,
          title: s.course.name,
          place: s.room,
          tag: s.sessionTypeLabel,
          exam: false,
        })),
        ...today.exams.map((e) => ({
          key: e.id,
          at: e.startsAt,
          end: e.endsAt,
          title: e.course.name,
          place: e.room,
          tag: 'Thi',
          exam: true,
        })),
      ].sort((a, b) => a.at.localeCompare(b.at))
    : [];

  // Việc nên làm tiếp theo: câu sai đến hạn > kỳ thi sắp tới > tạo đề mới.
  const next =
    due > 0
      ? { label: `Ôn ${due} câu đến hạn`, note: 'Ôn lại đúng lúc để nhớ lâu hơn.', to: '/sinh-vien/on-tap/so-cau-sai' }
      : nextExam
        ? {
            label: `Ôn cho kỳ thi ${nextExam.course.code}`,
            note: nextExam.daysLeft === 0 ? 'Thi hôm nay.' : `Còn ${nextExam.daysLeft} ngày.`,
            to: `/sinh-vien/on-tap?tab=ke-hoach#${nextExam.id}`,
          }
        : {
            label: 'Tạo đề ôn mới',
            note: 'Trắc nghiệm từ giáo trình, tự lưu lại câu sai.',
            to: '/sinh-vien/on-tap',
          };

  return (
    <div className="stack sh">
      <header className="sh-hero">
        <div className="sh-hero__who">
          <p className="sh-hero__date">{todayLabel()}</p>
          <h1 className="sh-hero__title">Chào {user?.fullName ?? ''}</h1>
          {profile && (
            <p className="sh-hero__meta">
              <span className="mono">{profile.studentCode}</span>
              {profile.studyClass && <> · Lớp {profile.studyClass.code}</>}
              {profile.cohort && <> · Khóa {profile.cohort}</>}
              {profile.trainingSystem && <> · {profile.trainingSystem}</>}
            </p>
          )}
        </div>
        {loaded && (
          <Link to={next.to} className="sh-hero__next">
            <span className="sh-hero__next-label">Việc tiếp theo</span>
            <span className="sh-hero__next-title">
              {next.label}
              <Icon name="arrow" size={18} />
            </span>
            <span className="sh-hero__next-note">{next.note}</span>
          </Link>
        )}
      </header>

      {progress && (
        <ul className="sh-kpis" aria-label="Tiến trình ôn tập">
          {metrics.map((m) => {
            const inner = (
              <>
                <span className="sh-kpi__label">{m.label}</span>
                <span className={`sh-kpi__value${m.tone ? ` sh-kpi__value--${m.tone}` : ''}`}>{m.value}</span>
                <span className="sh-kpi__hint">{m.hint}</span>
              </>
            );
            return (
              <li key={m.label} className="sh-kpi">
                {m.to ? (
                  <Link to={m.to} className="sh-kpi__body sh-kpi__body--link">
                    {inner}
                  </Link>
                ) : (
                  <div className="sh-kpi__body">{inner}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <div className="sh-grid">
        <div className="sh-col">
          <section className="sheet sheet--pad sh-grid__progress">
            <div className="section-head">
              <h2 className="aside-h">Tiến trình theo môn</h2>
              <Link to="/sinh-vien/on-tap" className="section-head__link">
                Tạo đề ôn
              </Link>
            </div>
            {!loaded ? (
              <p className="eyebrow">Đang tải…</p>
            ) : !progress || progress.courses.length === 0 ? (
              <div className="empty">
                <p className="empty__title">Chưa có dữ liệu ôn tập</p>
                <p>
                  Làm một đề trắc nghiệm từ giáo trình, tiến trình từng môn sẽ hiện ở đây.{' '}
                  <Link to="/sinh-vien/on-tap">Bắt đầu ôn tập</Link>
                </p>
              </div>
            ) : (
              <ul className="prog">
                {progress.courses.map((c) => {
                  const pct = c.avgScore === null ? 0 : Math.round(c.avgScore * 10);
                  return (
                    <li key={c.course.id} className="prog__row">
                      <div className="prog__head">
                        <span className="prog__name">
                          <span className="mono">{c.course.code}</span> — {c.course.name}
                        </span>
                        {c.reviewDue > 0 && <span className="tag tag--warn">{c.reviewDue} câu đến hạn</span>}
                      </div>
                      <div
                        className="prog__track"
                        role="img"
                        aria-label={
                          c.avgScore === null ? 'Chưa có điểm' : `Điểm trung bình ${viScore(c.avgScore)} trên 10`
                        }
                      >
                        <span className={`prog__fill${scoreTone(c.avgScore)}`} style={{ width: `${pct}%` }} />
                      </div>
                      <p className="prog__meta">
                        {c.sessions} lượt
                        {c.avgScore !== null && <> · TB {viScore(c.avgScore)}</>}
                        {c.lastScore !== null && <> · gần nhất {viScore(c.lastScore)}</>}
                        {c.mastered > 0 && <> · đã thuộc {c.mastered} câu</>}
                        {' · '}
                        <Link to={`/sinh-vien/on-tap?mon=${c.course.id}`}>Ôn môn này</Link>
                      </p>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>

        <div className="sh-col">
          <section className="sheet sheet--pad sh-grid__today home-aside">
            <h2 className="aside-h">Hôm nay</h2>
            {!today ? (
              <p className="home-aside__empty">{loaded ? 'Chưa gắn với lớp nên chưa có lịch.' : 'Đang tải…'}</p>
            ) : entries.length === 0 ? (
              <p className="home-aside__empty">Hôm nay không có buổi học hay ca thi.</p>
            ) : (
              <ol className="today">
                {entries.map((e) => (
                  <li key={e.key} className="today__item">
                    <span className="today__time mono">
                      {hhmm(e.at)}–{hhmm(e.end)}
                    </span>
                    <span className="today__body">
                      <span className="today__title">{e.title}</span>
                      <span className="today__meta">
                        {e.exam ? <span className="tag tag--seal">Thi</span> : e.tag}
                        <span>{e.place || 'Chưa xếp phòng'}</span>
                      </span>
                    </span>
                  </li>
                ))}
              </ol>
            )}
            <Link to="/sinh-vien/lich" className="home-aside__more">
              Xem lịch tuần
            </Link>
          </section>

          {progress && (
            <section className="sheet sheet--pad sh-grid__activity">
              <div className="section-head">
                <h2 className="aside-h">Nhịp ôn 14 ngày</h2>
                <span className="section-head__note">{progress.totalSessions} lượt từ trước đến nay</span>
              </div>
              <ActivityBars data={progress.activity} />
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
