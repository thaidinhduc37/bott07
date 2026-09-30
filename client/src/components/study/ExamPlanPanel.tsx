import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Icon } from '@/components/shared/Icon';
import type { ExamPlanItem } from '@/services/learning-api';
import { MONTHS, READINESS_TAG, rangeLabel, viScore } from './format';

/**
 * Nội dung tab "Kế hoạch ôn thi": một dòng cho mỗi kỳ thi trong 120 ngày tới,
 * bấm mở chi tiết (số liệu ôn tập + timeline ngày ôn) ngay bên dưới. Trang cha
 * đã có H1/dòng phụ nên ở đây chỉ giữ phần thân. Các nút "Tạo đề ôn" không điều
 * hướng — gọi `onStartQuiz` để trang cha chuyển sang tab Ôn tập và điền sẵn.
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
    <div
      className="page-grid page-grid--aside-left"
      style={{ ['--aside-w' as string]: '24rem' }}
    >
      <aside className="page-grid__aside">
        <div className="sheet plan-list">
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
  const daysLeft = exam.daysLeft;

  return (
    <div id={exam.id} className={`plan-row${open ? ' plan-row--open' : ''}`}>
      <button
        type="button"
        className="plan-row__head"
        aria-expanded={open}
        aria-current={open ? 'true' : undefined}
        onClick={onToggle}
      >
        <span className="plan-row__date" aria-hidden="true">
          <span className="plan-row__day">{d.getDate()}</span>
          <span className="plan-row__month">{MONTHS[d.getMonth()]}</span>
        </span>
        <span className="plan-row__body">
          <span className="plan-row__title">
            <span className="mono">{exam.course.code}</span> — {exam.course.name}
          </span>
          <span className="plan-row__desc">
            {daysLeft === 0 ? 'Hôm nay' : `còn ${daysLeft} ngày`}
          </span>
        </span>
        <span className={`tag ${readiness.cls}`}>{readiness.label}</span>
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
  const time = new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit' }).format(
    new Date(exam.startsAt),
  );

  return (
    <div className={`plan-detail${inline ? ' plan-detail--inline' : ' sheet'}`}>
      <h2 className="plan-detail__title">
        <span className="mono">{exam.course.code}</span> — {exam.course.name}
      </h2>

      <p className="plan-detail__info">
        {exam.formatLabel}
        {exam.room && <> · Phòng {exam.room}</>}
        {exam.building && <> ({exam.building})</>}
        {time && <> · {time}</>}
        {exam.durationMinutes > 0 && <> · {exam.durationMinutes} phút</>}
      </p>

      <p className="plan-detail__stats">
        <span>
          <strong>{exam.progress.quizCount}</strong> lượt ôn
        </span>
        <span>
          <strong>{exam.progress.avgScore != null ? viScore(exam.progress.avgScore) : '—'}</strong> điểm TB
        </span>
        <span>
          <strong>{exam.progress.reviewDue}</strong> câu sai đến hạn
        </span>
      </p>

      {exam.allowedMaterials && <p className="plan-detail__materials">Được mang vào: {exam.allowedMaterials}</p>}

      {exam.plan.length === 0 ? (
        <p className="plan-detail__today">Hôm nay thi — chúc bạn làm bài tốt.</p>
      ) : (
        <ol className="plan-timeline">
          {exam.plan.map((day, i) => {
            const isToday = day.from <= today && today <= day.to;
            return (
              <li key={`${day.from}-${i}`} className={`plan-timeline__item${isToday ? ' plan-timeline__item--today' : ''}`}>
                <span className="plan-timeline__dot" aria-hidden="true" />
                <div className="plan-timeline__body">
                  <p className="plan-timeline__date">
                    {rangeLabel(day.from, day.to)}
                    {isToday && <span className="plan-timeline__today">Hôm nay</span>}
                  </p>
                  <p className="plan-timeline__title">{day.title}</p>
                  {day.kind === 'DOC' && day.suggestedTopic && (
                    <button
                      type="button"
                      className="plan-timeline__link"
                      onClick={() => onStartQuiz({ courseId: exam.course.id, topic: day.suggestedTopic ?? undefined })}
                    >
                      Tạo đề ôn
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}

      <div className="plan-detail__actions">
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
