import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Icon } from '@/components/shared/Icon';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { ApiError } from '@/services/api';
import { chatApi, type CourseRef } from '@/services/chat-api';
import {
  learningApi,
  type ExamPlanItem,
  type QuizSummary,
  type ReviewOverview,
} from '@/services/learning-api';
import { PageHeader } from '@/components/shared/PageHeader';
import { TabPanel, Tabs } from '@/components/shared/Tabs';
import { ExamPlanPanel } from '@/components/study/ExamPlanPanel';
import { QuizComposer, type QuizDraft } from '@/components/study/QuizComposer';
import { dayLabel, READINESS_TAG, viScore } from '@/components/study/format';

const DATE = new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short' });

type Tab = 'on-tap' | 'ke-hoach';

/**
 * Ôn tập từ giáo trình. Câu hỏi sinh từ chính giáo trình đã nạp, qua cùng ngưỡng
 * tin cậy với hỏi đáp: chủ đề không có trong giáo trình thì hệ thống từ chối
 * chứ không bịa câu hỏi. Gộp hai trang cũ (Ôn tập + Kế hoạch ôn thi) thành một
 * trang với hai tab; form "Tạo đề" chỉ còn một bản ở tab Ôn tập.
 */
export default function StudyHubPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab: Tab = searchParams.get('tab') === 'ke-hoach' ? 'ke-hoach' : 'on-tap';
  useDocumentTitle(tab === 'ke-hoach' ? 'Kế hoạch ôn thi' : 'Ôn tập');
  const navigate = useNavigate();

  const [courses, setCourses] = useState<CourseRef[]>([]);
  const [history, setHistory] = useState<QuizSummary[] | null>(null);
  const [review, setReview] = useState<ReviewOverview | null>(null);
  const [examPlan, setExamPlan] = useState<{ today: string; exams: ExamPlanItem[]; reason?: 'NO_CLASS' } | null>(null);
  const [examPlanError, setExamPlanError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [, setError] = useState<string | null>(null);

  // Form "Tạo đề" do trang cha giữ (controlled) để các nút "Tạo đề ôn" ở tab
  // Kế hoạch có thể điền sẵn môn/chủ đề rồi chuyển sang tab Ôn tập.
  const [draft, setDraft] = useState<QuizDraft>(() => ({
    topic: searchParams.get('chuDe') ?? '',
    courseId: searchParams.get('mon') ?? '',
  }));
  const topicInputRef = useRef<HTMLInputElement | null>(null);
  // Yêu cầu "focus ô Chủ đề" từ tab Kế hoạch. Không thể focus ngay: lúc đó form của tab
  // Ôn tập chưa được dựng (đổi tab là một lần render sau). Cờ + effect bên dưới đợi tới khi
  // đang ở tab Ôn tập rồi mới focus; `focusTick` để effect chạy lại cả khi tab không đổi.
  const pendingFocus = useRef(false);
  const [focusTick, setFocusTick] = useState(0);

  useEffect(() => {
    void chatApi.courses().then((r) => setCourses(r.items)).catch(() => setCourses([]));
    void learningApi.sessions().then((r) => setHistory(r.items)).catch(() => setHistory([]));
    void learningApi.reviewItems().then(setReview).catch(() => setReview(null));
    // Một lần gọi duy nhất, dùng chung cho cột phụ "Kỳ thi sắp tới" và tab Kế hoạch.
    void learningApi
      .examPlan()
      .then((r) => {
        setExamPlan(r);
        // Địa chỉ dạng `/on-tap#<id kỳ thi>` (không có ?tab=): mở tab Kế hoạch. Phải dùng
        // navigate với `hash` tường minh — `setSearchParams` xóa mất `#id`, khiến panel
        // không còn biết kỳ nào cần mở. Đã ở tab Kế hoạch rồi thì không đụng tới URL.
        const fromHash = window.location.hash.slice(1);
        if (fromHash && searchParams.get('tab') !== 'ke-hoach' && r.exams.some((x) => x.id === fromHash)) {
          navigate({ search: '?tab=ke-hoach', hash: `#${fromHash}` }, { replace: true });
        }
      })
      .catch((e) => setExamPlanError(e instanceof ApiError ? e.message : 'Không tải được kế hoạch ôn thi'));
  }, []);

  async function onReview() {
    setBusy(true);
    setError(null);
    try {
      const s = await learningApi.createReview();
      navigate(`/sinh-vien/on-tap/${s.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không tạo được lượt ôn');
      setBusy(false);
    }
  }

  function setTab(next: Tab) {
    // Về tab Ôn tập: xóa lỗi/lượt ôn cũ để mỗi lần đổi tab là một lần mới.
    if (next === 'on-tap') {
      setError(null);
      setBusy(false);
    }
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        if (next === 'on-tap') p.delete('tab');
        else p.set('tab', next);
        return p;
      },
      { replace: false },
    );
  }

  // Từ tab Kế hoạch: điền sẵn môn (+ chủ đề nếu có), chuyển sang tab Ôn tập,
  // rồi khi panel hiển thị cuộn tới form và focus ô Chủ đề.
  function startQuizFromPlan(d: { courseId: string; topic?: string }) {
    setDraft({ courseId: d.courseId, topic: d.topic ?? draft.topic });
    pendingFocus.current = true;
    setFocusTick((t) => t + 1);
    setTab('on-tap');
  }

  useEffect(() => {
    if (!pendingFocus.current || tab !== 'on-tap') return;
    pendingFocus.current = false;
    const el = topicInputRef.current;
    el?.focus();
    el?.scrollIntoView({ block: 'center' });
  }, [focusTick, tab]);

  const exams = examPlan?.exams ?? [];
  const upcomingCount = exams.filter((e) => e.daysLeft <= 14).length;

  return (
    <div className="stack">
      <PageHeader
        title="Ôn tập"
        description="Tạo đề trắc nghiệm từ giáo trình và theo dõi kế hoạch ôn cho từng kỳ thi."
        tabs={
          <Tabs
            idPrefix="on-tap"
            label="Nội dung trang Ôn tập"
            value={tab}
            onChange={setTab}
            items={[
              { id: 'on-tap', label: 'Ôn tập' },
              {
                id: 'ke-hoach',
                label: 'Kế hoạch ôn thi',
                ...(upcomingCount > 0 && {
                  badge: upcomingCount,
                  badgeLabel: `${upcomingCount} kỳ thi trong 14 ngày tới`,
                }),
              },
            ]}
          />
        }
      />

      {tab === 'on-tap' ? (
        <TabPanel idPrefix="on-tap" tab="on-tap">
          <div className="page-grid">
            <div className="page-grid__main">
              <QuizComposer
                courses={courses}
                draft={draft}
                onDraftChange={setDraft}
                topicInputRef={topicInputRef}
              />

              <section className="stack">
                <h2 className="display" style={{ fontSize: '1.15rem', margin: 0 }}>
                  Các lượt đã làm
                </h2>

                {history === null ? (
                  <p className="eyebrow">Đang tải…</p>
                ) : history.length === 0 ? (
                  <div className="empty">
                    <span className="empty__icon" aria-hidden="true">
                      <Icon name="book" size={22} />
                    </span>
                    <p className="empty__title">Chưa có lượt ôn tập nào</p>
                    <p>Tạo đề đầu tiên ở trên.</p>
                  </div>
                ) : (
                  <div className="sheet action-list">
                    {history.slice(0, 10).map((s) => (
                      <Link key={s.id} to={`/sinh-vien/on-tap/${s.id}`} className="action-row study-hist">
                        <span className="action-row__body">
                          <span className="action-row__title">{s.topic ?? 'Ôn lại câu sai'}</span>
                          <span className="action-row__desc">
                            <span className="mono">{s.course?.code ?? '—'}</span>
                            {' · '}
                            {DATE.format(new Date(s.createdAt))}
                          </span>
                        </span>
                        <span className="study-hist__score">
                          {s.status === 'SUBMITTED' ? (
                            <span>{viScore(s.score ?? 0)}</span>
                          ) : (
                            <span className="tag tag--warn">Đang làm</span>
                          )}
                        </span>
                      </Link>
                    ))}
                  </div>
                )}
              </section>
            </div>

            <aside className="page-grid__aside">
              <section className="sheet sheet--pad study-aside">
                <h2 className="aside-h">Sổ câu sai</h2>
                {review ? (
                  <>
                    <p className="study-aside__due">
                      <strong>{review.due}</strong>
                      <span>câu đến hạn</span>
                    </p>
                    <p className="study-aside__meta">
                      {review.learning} đang học · {review.mastered} đã thuộc
                    </p>
                    {review.due > 0 ? (
                      <button type="button" className="btn btn--primary btn--block" onClick={onReview} disabled={busy}>
                        Ôn {review.due} câu đến hạn
                      </button>
                    ) : (
                      <p className="field__hint" style={{ margin: 0 }}>
                        Không có câu nào đến hạn hôm nay.
                      </p>
                    )}
                    <Link to="/sinh-vien/on-tap/so-cau-sai" className="study-aside__link">
                      Mở sổ câu sai
                    </Link>
                  </>
                ) : (
                  <p className="eyebrow">Đang tải…</p>
                )}
              </section>

              {exams.length > 0 && (
                <section className="sheet sheet--pad study-aside">
                  <h2 className="aside-h">Kỳ thi sắp tới</h2>
                  <ul className="study-exams">
                    {exams.slice(0, 3).map((e) => {
                      const r = READINESS_TAG[e.progress.readiness];
                      return (
                        <li key={e.id}>
                          <button
                            type="button"
                            className="study-exam"
                            onClick={() => startQuizFromPlan({ courseId: e.course.id })}
                          >
                            <span className="study-exam__body">
                              <span className="study-exam__title">
                                <span className="mono">{e.course.code}</span> — {e.course.name}
                              </span>
                              <span className="study-exam__meta">
                                {dayLabel(e.examDate)} · còn {e.daysLeft} ngày
                              </span>
                            </span>
                            <span className={`tag ${r.cls}`}>{r.label}</span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                  <button type="button" className="study-aside__link" onClick={() => setTab('ke-hoach')}>
                    Xem kế hoạch ôn thi
                  </button>
                </section>
              )}
            </aside>
          </div>
        </TabPanel>
      ) : (
        <TabPanel idPrefix="on-tap" tab="ke-hoach">
          <ExamPlanPanel
            plan={examPlan}
            error={examPlanError}
            onStartQuiz={startQuizFromPlan}
          />
        </TabPanel>
      )}
    </div>
  );
}
