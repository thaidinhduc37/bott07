import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Icon, type IconName } from '@/components/shared/Icon';
import { Metrics, type Metric } from '@/components/shared/Metrics';
import { PageHeader } from '@/components/shared/PageHeader';
import { useSession } from '@/components/shared/SessionProvider';
import { viScore } from '@/components/study/format';
import { approvalsApi } from '@/services/approvals-api';
import { documentsApi } from '@/services/documents-api';
import { insightsApi, type InsightCourse } from '@/services/learning-api';
import { scheduleApi, type ScheduleEntry } from '@/services/schedule-api';

interface DocStats {
  total: number;
  failed: number;
}

const hhmm = (iso: string) =>
  new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(iso));

const isoDay = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

export default function StaffHome() {
  const { user } = useSession();
  const has = useCallback((r: string) => user?.roles.includes(r as never) ?? false, [user]);
  const teaches = has('ACADEMIC_MANAGER') || has('LECTURER');
  const approves = has('APPROVER') || has('ACADEMIC_MANAGER');

  // Mỗi nguồn tải độc lập, lỗi thì bỏ riêng mục đó (null = chưa có / không lấy được).
  const [pending, setPending] = useState<number | null>(null);
  const [docs, setDocs] = useState<DocStats | null>(null);
  const [today, setToday] = useState<ScheduleEntry[] | null>(null);
  const [upcomingExams, setUpcomingExams] = useState<number | null>(null);
  const [courses, setCourses] = useState<InsightCourse[] | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const jobs: Promise<unknown>[] = [];
    if (approves) {
      jobs.push(approvalsApi.inbox(false).then((r) => setPending(r.items.length)));
    }
    if (teaches) {
      jobs.push(
        Promise.all([documentsApi.list().catch(() => null), documentsApi.indexStatus().catch(() => null)]).then(
          ([list, status]) => {
            if (!list && !status) return;
            const total =
              list?.total ??
              Object.values(status?.postgres ?? {}).reduce((n, s) => n + (s?.versions ?? 0), 0);
            setDocs({ total, failed: status?.postgres.FAILED?.versions ?? 0 });
          },
        ),
      );
      const now = new Date();
      const week = new Date(now);
      week.setDate(week.getDate() + 6);
      jobs.push(
        scheduleApi.teaching({ from: isoDay(now), to: isoDay(week) }).then((t) => {
          const day = isoDay(now);
          const all: ScheduleEntry[] = [...t.sessions, ...t.exams];
          setToday(
            all
              .filter((e) => isoDay(new Date(e.startsAt)) === day)
              .sort((a, b) => a.startsAt.localeCompare(b.startsAt)),
          );
          setUpcomingExams(t.exams.length);
        }),
      );
      jobs.push(insightsApi.courses().then((r) => setCourses(r.items)));
    }
    void Promise.allSettled(jobs).then(() => setLoaded(true));
  }, [approves, teaches]);

  const totalSessions = courses?.reduce((n, c) => n + c.sessions, 0) ?? 0;
  const metrics: Metric[] = [];
  if (teaches && today) {
    metrics.push({
      label: 'Buổi dạy hôm nay',
      value: today.filter((e) => e.kind === 'SESSION').length,
      hint: upcomingExams ? `${upcomingExams} ca thi trong 7 ngày tới` : 'Không có ca thi trong 7 ngày tới',
      to: '/can-bo/lich',
    });
  }
  if (approves && pending !== null) {
    metrics.push({
      label: 'Đơn chờ xử lý',
      value: pending,
      hint: pending > 0 ? 'Cần bạn xử lý' : 'Không có đơn nào',
      to: '/can-bo/don-cho-xu-ly',
      tone: pending > 0 ? 'warn' : undefined,
    });
  }
  if (teaches && courses) {
    metrics.push({
      label: 'Học viên ôn tập (30 ngày)',
      value: `${totalSessions} lượt`,
      hint: `${courses.length} môn phụ trách`,
      to: '/can-bo/hoc-tap',
    });
  }
  if (teaches && docs) {
    metrics.push({
      label: 'Tài liệu trong hệ thống',
      value: docs.total,
      hint: docs.failed > 0 ? `${docs.failed} tệp lập chỉ mục lỗi` : 'Đều đã lập chỉ mục',
      to: '/can-bo/tai-lieu',
      tone: docs.failed > 0 ? 'warn' : undefined,
    });
  }

  const links: { href: string; icon: IconName; label: string; show: boolean }[] = [
    { href: '/can-bo/don-cho-xu-ly', icon: 'inbox', label: 'Đơn chờ xử lý', show: approves },
    { href: '/can-bo/hoc-tap', icon: 'pulse', label: 'Tình hình học tập', show: teaches },
    { href: '/can-bo/tai-lieu', icon: 'folder', label: 'Tài liệu', show: teaches },
    { href: '/can-bo/lich', icon: 'calendar', label: 'Lịch học & lịch thi', show: teaches },
    { href: '/can-bo/hoi-dap', icon: 'chat', label: 'Hỏi đáp quy chế', show: true },
  ];

  return (
    <div className="stack">
      <PageHeader title={`Chào ${user?.fullName ?? ''}`} description={user?.roleNames.join(' · ')} />

      {metrics.length > 0 && <Metrics label="Tổng quan công việc" items={metrics} />}

      <div className="page-grid">
        <div className="page-grid__main">
          {teaches && (
            <section className="sheet sheet--pad">
              <div className="section-head">
                <h2 className="aside-h">Lịch dạy hôm nay</h2>
                <Link to="/can-bo/lich" className="section-head__link">
                  Mở lịch tuần
                </Link>
              </div>
              {!loaded && today === null ? (
                <p className="eyebrow">Đang tải…</p>
              ) : !today || today.length === 0 ? (
                <p className="home-aside__empty">Hôm nay không có buổi dạy hay ca thi nào của bạn.</p>
              ) : (
                <ol className="today today--wide">
                  {today.map((e) => (
                    <li key={e.id} className="today__item">
                      <span className="today__time mono">
                        {hhmm(e.startsAt)}–{hhmm(e.endsAt)}
                      </span>
                      <span className="today__body">
                        <span className="today__title">
                          {e.course.name}
                          {e.class && <span className="today__class"> · lớp {e.class.code}</span>}
                        </span>
                        <span className="today__meta">
                          {e.kind === 'EXAM' ? <span className="tag tag--seal">Thi</span> : e.sessionTypeLabel}
                          <span>{e.room || 'Chưa xếp phòng'}</span>
                          {e.lecturerNote ? (
                            <span className="tag tag--ok">Đã ghi yêu cầu</span>
                          ) : (
                            <Link to="/can-bo/lich" className="today__cta">
                              Ghi yêu cầu cho học viên
                            </Link>
                          )}
                        </span>
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          )}

          {teaches && courses && courses.length > 0 && (
            <section className="sheet sheet--pad">
              <div className="section-head">
                <h2 className="aside-h">Môn phụ trách</h2>
                <Link to="/can-bo/hoc-tap" className="section-head__link">
                  Xem chi tiết
                </Link>
              </div>
              <ul className="prog">
                {courses.map((c) => {
                  const pct = c.avgScore === null ? 0 : Math.round(c.avgScore * 10);
                  return (
                    <li key={c.course.id} className="prog__row">
                      <div className="prog__head">
                        <span className="prog__name">
                          <span className="mono">{c.course.code}</span> — {c.course.name}
                        </span>
                      </div>
                      <div
                        className="prog__track"
                        role="img"
                        aria-label={c.avgScore === null ? 'Chưa có điểm' : `Điểm trung bình ${viScore(c.avgScore)} trên 10`}
                      >
                        <span
                          className={`prog__fill${c.avgScore !== null && c.avgScore < 5 ? ' prog__fill--warn' : ''}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <p className="prog__meta">
                        {c.sessions === 0
                          ? 'Chưa có lượt ôn nào trong 30 ngày'
                          : `${c.sessions} lượt · ${c.learners} học viên${c.avgScore !== null ? ` · TB ${viScore(c.avgScore)}` : ''}`}
                        {' · '}
                        <Link to={`/can-bo/hoc-tap?mon=${c.course.id}`}>Phần học viên hay sai</Link>
                      </p>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
        </div>

        <aside className="page-grid__aside">
          <nav className="sheet sheet--pad quick" aria-label="Lối tắt">
            <h2 className="aside-h">Lối tắt</h2>
            <ul className="quick__list">
              {links
                .filter((l) => l.show)
                .map((l) => (
                  <li key={l.href}>
                    <Link to={l.href} className="quick__link">
                      <Icon name={l.icon} size={18} />
                      {l.label}
                    </Link>
                  </li>
                ))}
            </ul>
            {teaches && (
              <p className="quick__note">
                Số liệu học tập chỉ là số gộp, không hiện tên hay mã học viên.
              </p>
            )}
          </nav>
        </aside>
      </div>
    </div>
  );
}
