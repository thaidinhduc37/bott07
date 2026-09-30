import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Icon, type IconName } from '@/components/shared/Icon';
import { Metrics } from '@/components/shared/Metrics';
import { PageHeader } from '@/components/shared/PageHeader';
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

const LINKS: { href: string; icon: IconName; label: string }[] = [
  { href: '/sinh-vien/hoi-dap', icon: 'chat', label: 'Hỏi đáp' },
  { href: '/sinh-vien/on-tap', icon: 'book', label: 'Ôn tập' },
  { href: '/sinh-vien/so-tay', icon: 'pencil', label: 'Sổ tay' },
  { href: '/sinh-vien/lich', icon: 'calendar', label: 'Lịch học & lịch thi' },
  { href: '/sinh-vien/bieu-mau', icon: 'form', label: 'Lập đơn' },
];

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
  const metrics = progress
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
          tone: due > 0 ? ('warn' as const) : undefined,
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

  return (
    <div className="stack">
      <PageHeader
        title={`Chào ${user?.fullName ?? ''}`}
        description={
          profile ? (
            <>
              <span className="mono">{profile.studentCode}</span>
              {profile.studyClass && <> · Lớp {profile.studyClass.code}</>}
              {profile.cohort && <> · Khóa {profile.cohort}</>}
              {profile.trainingSystem && <> · {profile.trainingSystem}</>}
            </>
          ) : undefined
        }
      />

      {progress && <Metrics label="Tiến trình ôn tập" items={metrics} />}

      <div className="page-grid">
        <div className="page-grid__main">
          <section className="sheet sheet--pad">
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

          {progress && (
            <section className="sheet sheet--pad">
              <div className="section-head">
                <h2 className="aside-h">Nhịp ôn 14 ngày</h2>
                <span className="section-head__note">{progress.totalSessions} lượt từ trước đến nay</span>
              </div>
              <ActivityBars data={progress.activity} />
            </section>
          )}
        </div>

        <aside className="page-grid__aside">
          <section className="sheet sheet--pad home-aside">
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

          <nav className="sheet sheet--pad quick" aria-label="Lối tắt">
            <h2 className="aside-h">Lối tắt</h2>
            <ul className="quick__list">
              {LINKS.map((l) => (
                <li key={l.href}>
                  <Link to={l.href} className="quick__link">
                    <Icon name={l.icon} size={18} />
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
            <p className="quick__note">
              Lập đơn tự điền thông tin từ <Link to="/ho-so">hồ sơ của bạn</Link>. Sai thông tin thì báo Phòng Quản
              lý học viên.
            </p>
          </nav>
        </aside>
      </div>
    </div>
  );
}
