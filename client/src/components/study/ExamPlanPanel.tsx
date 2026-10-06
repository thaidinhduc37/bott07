import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Icon } from '@/components/shared/Icon';
import type { ExamPlanItem } from '@/services/learning-api';
import { MONTHS, READINESS_TAG, dayLabel, rangeLabel, viScore } from './format';

/**
 * Nội dung tab "Kế hoạch ôn thi": danh sách kỳ thi trong 120 ngày tới (cột trái) và chi tiết kỳ đang chọn
 * (cột phải: đếm ngược, thông tin ca thi, số liệu ôn tập, các bước ôn). Màn hẹp: mỗi dòng mở chi tiết ngay bên
 * dưới (accordion). Các nút "Tạo đề ôn" không điều hướng — gọi `onStartQuiz` để trang cha chuyển sang tab
 * "Làm đề" và điền sẵn.
 */
export function ExamPlanPanel(props: {
  plan: { today: string; exams: ExamPlanItem[]; reason?: 'NO_CLASS' } | null;
  error: string | null;
  onStartQuiz: (d: { courseId: string; topic?: string }) => void;
}) {
  const { plan, error, onStartQuiz } = props;
  const [openId, setOpenId] = useState<string | null>(null);

  // Khi dữ liệu về: mở kỳ theo `#<id>` trong URL (thông báo nhắc thi), nếu không mở kỳ
  // gần nhất. CHỈ cuộn khi vào bằng liên kết `#id`: trước đây cuộn kỳ đầu tiên lên đầu
  // màn hình ở MỌI lần hiện tab, nên bấm tab là trang nhảy và tiêu đề + thanh tab trôi mất.
  useEffect(() => {
    if (!plan) return;
    const fromHash = window.location.hash.slice(1);
    const target = plan.exams.find((x) => x.id === fromHash);
    setOpenId(target?.id ?? plan.exams[0]?.id ?? null);
    if (target) {
      requestAnimationFrame(() => document.getElementById(target.id)?.scrollIntoView({ block: 'nearest' }));
    }
  }, [plan]);

  if (error) {
    return (
      <div className="notice notice--error" role="alert">
        {error}
      </div>
    );
  }

  if (!plan) {
    return <p className="eyebrow">Đang tải…</p>;
  }

  if (plan.reason === 'NO_CLASS') {
    return (
      <div className="empty">
        <span className="empty__icon" aria-hidden="true">
          <Icon name="calendar" size={22} />
        </span>
        <p className="empty__title">Chưa có lịch thi</p>
        <p>Tài khoản chưa gắn với lớp nên chưa có lịch thi.</p>
      </div>
    );
  }

  if (plan.exams.length === 0) {
    return (
      <div className="empty">
        <span className="empty__icon" aria-hidden="true">
          <Icon name="calendar" size={22} />
        </span>
        <p className="empty__title">Chưa có lịch thi</p>
        <p>Chưa có lịch thi nào trong 120 ngày tới.</p>
      </div>
    );
  }

  return (
    <div className="page-grid page-grid--aside-left" style={{ ['--aside-w' as string]: '22rem' }}>
      <aside className="page-grid__aside">
        <div className="sheet xp-list">
          {plan.exams.map((exam) => (
            <ExamRow
              key={exam.id}
              exam={exam}
              today={plan.today}
              open={openId === exam.id}
              onToggle={() => setOpenId(openId === exam.id ? null : exam.id)}
            />
          ))}
        </div>
      </aside>

      <div className="page-grid__main">
        {(() => {
          // Luôn render chi tiết ở cột phải (ẩn bằng CSS ở màn hẹp) để giữ
          // đúng một bản chi tiết cho kỳ đang chọn; bản inline trong dòng
          // chỉ hiện ở màn hẹp.
          const exam = plan.exams.find((e) => e.id === openId) ?? plan.exams[0];
          return <ExamDetail exam={exam} today={plan.today} onStartQuiz={onStartQuiz} />;
        })()}
      </div>
    </div>
  );
}

function ExamRow({
  exam,
  today,
  open,
  onToggle,
}: {
  exam: ExamPlanItem;
  today: string;
  open: boolean;
  onToggle: () => void;
}) {
  const d = new Date(exam.examDate);
  const readiness = READINESS_TAG[exam.progress.readiness];

  return (
    <div id={exam.id} className={`xp-row${open ? ' xp-row--open' : ''}`}>
      <button
        type="button"
        className="xp-row__head"
        aria-expanded={open}
        aria-current={open ? 'true' : undefined}
        onClick={onToggle}
      >
        <span className="xp-date" aria-hidden="true">
          <span className="xp-date__day">{d.getDate()}</span>
          <span className="xp-date__month">{MONTHS[d.getMonth()]}</span>
        </span>
        <span className="xp-row__body">
          <span className="xp-row__title">
            <span className="mono">{exam.course.code}</span> — {exam.course.name}
          </span>
          <span className="xp-row__meta">
            <span>{exam.daysLeft === 0 ? 'Hôm nay' : `còn ${exam.daysLeft} ngày`}</span>
            <span className={`tag ${readiness.cls}`}>{readiness.label}</span>
          </span>
        </span>
      </button>

      {/* Chi tiết inline — chỉ hiện ở màn hẹp (accordion), ẩn khi có cột chi tiết bên phải. */}
      {open && <ExamDetail exam={exam} today={today} inline onStartQuiz={() => {}} />}
    </div>
  );
}

function ExamDetail({
  exam,
  today,
  inline,
  onStartQuiz,
}: {
  exam: ExamPlanItem;
  today: string;
  inline?: boolean;
  onStartQuiz: (d: { courseId: string; topic?: string }) => void;
}) {
  const time = new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit' }).format(new Date(exam.startsAt));
  const readiness = READINESS_TAG[exam.progress.readiness];
  const place = [exam.room && `Phòng ${exam.room}`, exam.building].filter(Boolean).join(' · ');

  const facts: { label: string; value: string }[] = [
    { label: 'Ngày thi', value: `${dayLabel(exam.examDate)} · ${time}` },
    { label: 'Thời lượng', value: exam.durationMinutes > 0 ? `${exam.durationMinutes} phút` : '' },
    { label: 'Hình thức', value: exam.formatLabel },
    { label: 'Địa điểm', value: place },
    { label: 'Được mang vào', value: exam.allowedMaterials ?? '' },
  ].filter((f) => f.value);

  return (
    <div className={`xp${inline ? ' xp--inline' : ' sheet'}`}>
      <header className="xp__head">
        <div className="xp__who">
          <h2 className="xp__title">
            <span className="mono">{exam.course.code}</span> — {exam.course.name}
          </h2>
          <span className={`tag ${readiness.cls}`}>{readiness.label}</span>
        </div>
        <p className="xp__count">
          {exam.daysLeft === 0 ? (
            <strong>Hôm nay</strong>
          ) : (
            <>
              <strong>{exam.daysLeft}</strong>
              <span>ngày nữa</span>
            </>
          )}
        </p>
      </header>

      <dl className="xp__facts">
        {facts.map((f) => (
          <div key={f.label} className="xp__fact">
            <dt>{f.label}</dt>
            <dd>{f.value}</dd>
          </div>
        ))}
      </dl>

      <ul className="xp__stats" aria-label="Số liệu ôn tập">
        <li>
          <strong>{exam.progress.quizCount}</strong>
          <span>lượt ôn</span>
        </li>
        <li>
          <strong>{exam.progress.avgScore != null ? viScore(exam.progress.avgScore) : '—'}</strong>
          <span>điểm TB</span>
        </li>
        <li>
          <strong>{exam.progress.reviewDue}</strong>
          <span>câu sai đến hạn</span>
        </li>
      </ul>

      <h3 className="xp__h">Kế hoạch ôn</h3>
      {exam.plan.length === 0 ? (
        <p className="xp__empty">Hôm nay thi — chúc bạn làm bài tốt.</p>
      ) : (
        <ol className="xp__steps">
          {exam.plan.map((day, i) => {
            const isToday = day.from <= today && today <= day.to;
            return (
              <li key={`${day.from}-${i}`} className={`xp-step${isToday ? ' xp-step--today' : ''}`}>
                <span className="xp-step__dot" aria-hidden="true" />
                <div className="xp-step__body">
                  <p className="xp-step__date">
                    {rangeLabel(day.from, day.to)}
                    {isToday && <span className="tag tag--pen">Hôm nay</span>}
                  </p>
                  <p className="xp-step__title">{day.title}</p>
                </div>
                {day.kind === 'DOC' && day.suggestedTopic && (
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => onStartQuiz({ courseId: exam.course.id, topic: day.suggestedTopic ?? undefined })}
                  >
                    Tạo đề ôn
                  </button>
                )}
              </li>
            );
          })}
        </ol>
      )}

      <div className="xp__actions">
        <button type="button" className="btn btn--primary" onClick={() => onStartQuiz({ courseId: exam.course.id })}>
          Tạo đề ôn môn này
        </button>
        <Link to="/sinh-vien/on-tap/so-cau-sai" className="btn btn--ghost">
          Ôn câu sai
        </Link>
      </div>
    </div>
  );
}
