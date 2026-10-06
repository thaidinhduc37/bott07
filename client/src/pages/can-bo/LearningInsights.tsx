import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageHeader } from '@/components/shared/PageHeader';
import { useSession } from '@/components/shared/SessionProvider';
import { viScore } from '@/components/study/format';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { ApiError } from '@/services/api';
import {
  insightsApi,
  type InsightCourse,
  type FeedbackReview,
  type InsightCourseDetail,
  type UnansweredQuestion,
} from '@/services/learning-api';

const errText = (e: unknown) => (e instanceof ApiError ? e.message : 'Không tải được số liệu');

/**
 * Tình hình học tập của các môn giảng viên phụ trách: chỉ số gộp, không có tên hay
 * mã học viên (backend cũng không trả). Mục đích là biết phần nào cần giảng lại.
 */
export default function LearningInsights() {
  useDocumentTitle('Tình hình học tập');
  const { user } = useSession();
  const sees = user?.roles.includes('ACADEMIC_MANAGER') || user?.roles.includes('ADMIN');
  const [params, setParams] = useSearchParams();
  const [courses, setCourses] = useState<InsightCourse[] | null>(null);
  const [windowDays, setWindowDays] = useState(30);
  const [detail, setDetail] = useState<InsightCourseDetail | null>(null);
  const [unanswered, setUnanswered] = useState<UnansweredQuestion[] | null>(null);
  const [feedback, setFeedback] = useState<FeedbackReview | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selected = params.get('mon') ?? courses?.[0]?.course.id ?? null;

  useEffect(() => {
    insightsApi
      .courses()
      .then((r) => {
        setCourses(r.items);
        setWindowDays(r.windowDays);
      })
      .catch((e) => setError(errText(e)));
    if (sees) {
      insightsApi
        .unanswered()
        .then((r) => setUnanswered(r.items))
        .catch(() => setUnanswered([]));
      insightsApi
        .feedback()
        .then(setFeedback)
        .catch(() => setFeedback(null));
    }
  }, [sees]);

  useEffect(() => {
    if (!selected) return;
    setDetail(null);
    insightsApi
      .course(selected)
      .then(setDetail)
      .catch((e) => setError(errText(e)));
  }, [selected]);

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Giảng dạy"
        title="Tình hình học tập"
        description={`Số liệu ${windowDays} ngày gần nhất của học viên ở các môn bạn phụ trách. Chỉ có số gộp, không hiện tên hay mã học viên.`}
      />

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      {courses && courses.length === 0 ? (
        <div className="empty">
          <p className="empty__title">Chưa có môn nào</p>
          <p>Tài khoản chưa được gán môn học phụ trách nên chưa có số liệu.</p>
        </div>
      ) : (
        <div className="page-grid page-grid--aside-left" style={{ ['--aside-w' as string]: '20rem' }}>
          <aside className="page-grid__aside">
            <div className="sheet plan-list" role="list" aria-label="Môn học">
              {(courses ?? []).map((c) => {
                const on = c.course.id === selected;
                return (
                  <button
                    key={c.course.id}
                    type="button"
                    role="listitem"
                    className={`insight-course${on ? ' insight-course--on' : ''}`}
                    aria-current={on ? 'true' : undefined}
                    onClick={() => setParams({ mon: c.course.id }, { replace: true })}
                  >
                    <span className="insight-course__name">
                      <span className="mono">{c.course.code}</span> — {c.course.name}
                    </span>
                    <span className="insight-course__meta">
                      {c.sessions === 0
                        ? 'Chưa có lượt ôn'
                        : `${c.sessions} lượt · ${c.learners} học viên${c.avgScore !== null ? ` · TB ${viScore(c.avgScore)}` : ''}`}
                    </span>
                  </button>
                );
              })}
              {!courses && <p className="eyebrow insight-course__loading">Đang tải…</p>}
            </div>
          </aside>

          <div className="page-grid__main">
            {!detail ? (
              <p className="eyebrow">{selected ? 'Đang tải…' : ''}</p>
            ) : (
              <>
                <section className="sheet sheet--pad">
                  <div className="section-head">
                    <h2 className="aside-h">Câu nhiều học viên làm sai</h2>
                  </div>
                  {detail.hardQuestions.length === 0 ? (
                    <p className="home-aside__empty">
                      Chưa có câu nào có từ {detail.minLearners} học viên trở lên cùng sai. Số liệu ít hơn ngưỡng này
                      không được hiển thị để tránh đoán ra từng người.
                    </p>
                  ) : (
                    <ol className="hard">
                      {detail.hardQuestions.map((q, i) => (
                        <li key={i} className="hard__item">
                          <p className="hard__q">{q.question}</p>
                          {q.correctAnswer && <p className="hard__a">Đáp án đúng: {q.correctAnswer}</p>}
                          <p className="hard__meta">
                            <span className="tag tag--warn">{q.learners} học viên sai</span> · {q.timesWrong} lượt sai
                            {q.sourceFile && (
                              <>
                                {' · '}
                                {q.sourceFile}
                                {q.sourcePage ? `, tr. ${q.sourcePage}` : ''}
                              </>
                            )}
                          </p>
                        </li>
                      ))}
                    </ol>
                  )}
                </section>

                <section className="sheet sheet--pad">
                  <div className="section-head">
                    <h2 className="aside-h">Chủ đề học viên hay ôn</h2>
                  </div>
                  {detail.topics.length === 0 ? (
                    <p className="home-aside__empty">Chưa có lượt ôn nào theo chủ đề trong {detail.windowDays} ngày.</p>
                  ) : (
                    <ul className="prog">
                      {detail.topics.map((t) => (
                        <li key={t.topic} className="prog__row">
                          <div className="prog__head">
                            <span className="prog__name">{t.topic}</span>
                          </div>
                          <div className="prog__track" role="img" aria-label={t.avgScore === null ? 'Chưa có điểm' : `Điểm trung bình ${viScore(t.avgScore)} trên 10`}>
                            <span
                              className={`prog__fill${t.avgScore !== null && t.avgScore < 5 ? ' prog__fill--warn' : ''}`}
                              style={{ width: `${t.avgScore === null ? 0 : Math.round(t.avgScore * 10)}%` }}
                            />
                          </div>
                          <p className="prog__meta">
                            {t.sessions} lượt · {t.learners} học viên
                            {t.avgScore !== null && <> · TB {viScore(t.avgScore)}</>}
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </>
            )}

            {sees && feedback && (
              <section className="sheet sheet--pad">
                <div className="section-head">
                  <h2 className="aside-h">Phản hồi về trợ lý</h2>
                  <span className="section-head__note">{feedback.windowDays} ngày gần nhất</span>
                </div>
                {feedback.up + feedback.down === 0 ? (
                  <p className="home-aside__empty">Chưa có phản hồi nào.</p>
                ) : (
                  <>
                    <p className="hard__meta" style={{ marginBottom: 'var(--gap-4)' }}>
                      <span className="tag tag--ok">{feedback.up} hữu ích</span>{' '}
                      <span className="tag tag--warn">{feedback.down} chưa đúng</span>
                      {feedback.helpfulRate !== null && <> · {Math.round(feedback.helpfulRate * 100)}% hữu ích</>}
                      {feedback.byReason.length > 0 && (
                        <> · {feedback.byReason.map((r) => `${r.label}: ${r.count}`).join('; ')}</>
                      )}
                    </p>
                    {feedback.items.length > 0 && (
                      <ul className="hard">
                        {feedback.items.map((f, i) => (
                          <li key={i} className="hard__item">
                            <p className="hard__q">{f.question ?? '(không tìm thấy câu hỏi)'}</p>
                            <p className="hard__a" style={{ color: 'var(--ink-soft)' }}>
                              {f.abstained ? 'Trợ lý từ chối: ' : 'Trợ lý trả lời: '}
                              {f.answer.length > 220 ? `${f.answer.slice(0, 220)}…` : f.answer}
                            </p>
                            <p className="hard__meta">
                              {f.reasonLabel && <span className="tag tag--warn">{f.reasonLabel}</span>}
                              {f.comment && <> “{f.comment}”</>}
                              {' · '}
                              {f.mode === 'QUYCHE' ? 'Quy chế' : 'Giáo trình'} ·{' '}
                              {new Date(f.createdAt).toLocaleDateString('vi-VN')}
                            </p>
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                )}
              </section>
            )}

            {sees && unanswered && (
              <section className="sheet sheet--pad">
                <div className="section-head">
                  <h2 className="aside-h">Câu hỏi hệ thống chưa trả lời được</h2>
                  <span className="section-head__note">{windowDays} ngày gần nhất</span>
                </div>
                {unanswered.length === 0 ? (
                  <p className="home-aside__empty">Không có câu hỏi nào bị từ chối.</p>
                ) : (
                  <ul className="hard">
                    {unanswered.map((u, i) => (
                      <li key={i} className="hard__item">
                        <p className="hard__q">{u.question}</p>
                        <p className="hard__meta">
                          {u.mode === 'QUYCHE' ? 'Quy chế' : 'Giáo trình'} ·{' '}
                          {new Date(u.createdAt).toLocaleDateString('vi-VN')}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
