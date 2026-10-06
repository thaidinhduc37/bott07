import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Icon } from '@/components/shared/Icon';
import { PageHeader } from '@/components/shared/PageHeader';
import { SaveToNotebook } from '@/components/shared/SaveToNotebook';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { viScore } from '@/components/study/format';
import { ApiError } from '@/services/api';
import { learningApi, type QuizQuestion, type QuizSession } from '@/services/learning-api';

const LETTERS = ['A', 'B', 'C', 'D'];

/** Làm bài (chưa nộp) và xem kết quả (đã nộp) — cùng một địa chỉ. */
export default function QuizTakePage() {
  const { id = '' } = useParams();
  const [session, setSession] = useState<QuizSession | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmEmpty, setConfirmEmpty] = useState(false);

  useDocumentTitle(session?.topic ?? 'Ôn tập');

  useEffect(() => {
    setSession(null);
    setAnswers({});
    setError(null);
    setConfirmEmpty(false);
    learningApi
      .session(id)
      .then(setSession)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Không mở được lượt ôn tập'));
  }, [id]);

  async function onSubmit() {
    if (!session || busy) return;
    setBusy(true);
    setError(null);
    setConfirmEmpty(false);
    try {
      const graded = await learningApi.submit(
        session.id,
        session.questions.map((q) => ({ questionId: q.id, selectedIndex: answers[q.id] ?? null })),
      );
      setSession(graded);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không nộp được bài');
    } finally {
      setBusy(false);
    }
  }

  if (!session) {
    return (
      <div className="stack">
        {error ? (
          <div className="notice notice--error" role="alert">
            {error}
          </div>
        ) : (
          <p className="eyebrow">Đang tải…</p>
        )}
        <p>
          <Link to="/sinh-vien/on-tap" className="btn btn--ghost">
            Về trang ôn tập
          </Link>
        </p>
      </div>
    );
  }

  const done = session.status === 'SUBMITTED';
  const answered = Object.keys(answers).length;
  const total = session.questions.length;
  const correct = session.questions.filter((q) => q.isCorrect).length;
  const blank = total - answered;

  const navCells = session.questions.map((q, i) => {
    const picked = answers[q.id] != null;
    const tone = done ? (q.isCorrect ? 'ok' : q.selectedIndex != null ? 'seal' : 'muted') : picked ? 'on' : 'off';
    const label = done
      ? `Câu ${i + 1}, ${q.isCorrect ? 'đúng' : q.selectedIndex != null ? 'sai' : 'bỏ trống'}`
      : `Câu ${i + 1}, ${picked ? 'đã chọn' : 'chưa chọn'}`;
    return (
      <a key={q.id} href={`#cau-${i + 1}`} className={`quiz-cell quiz-cell--${tone}`} aria-label={label}>
        {i + 1}
      </a>
    );
  });

  return (
    <div className="stack">
      <PageHeader
        breadcrumb={[
          { label: 'Ôn tập', to: '/sinh-vien/on-tap' },
          { label: session.course ? `Lượt ôn · ${session.course.code}` : 'Lượt ôn' },
        ]}
        title={session.topic ?? 'Ôn lại câu sai'}
        description={
          done ? undefined : `${total} câu · chọn một đáp án cho mỗi câu. Câu bỏ trống tính là sai.`
        }
      />

      {/* Đang làm: màn hẹp đưa khối Tiến độ xuống cuối — nó dính đáy màn hình làm thanh nộp bài. */}
      <div className={`page-grid${done ? '' : ' page-grid--aside-last quiz-taking'}`}>
        <div className="page-grid__main">
          {error && (
            <div className="notice notice--error" role="alert">
              {error}
            </div>
          )}

          <div className="sheet quiz-sheet">
            <ol className="quiz-list">
              {session.questions.map((q, i) => (
                <li key={q.id} id={`cau-${i + 1}`} className="quiz-q">
                  <QuestionCard
                    q={q}
                    done={done}
                    selected={done ? (q.selectedIndex ?? null) : (answers[q.id] ?? null)}
                    onPick={(idx) => setAnswers((a) => ({ ...a, [q.id]: idx }))}
                  />
                </li>
              ))}
            </ol>
          </div>

          {done && (
            <div className="quiz-bar quiz-bar--static">
              <Link to="/sinh-vien/on-tap" className="btn btn--ghost">
                Về trang ôn tập
              </Link>
              <Link to="/sinh-vien/on-tap" className="btn btn--primary">
                Tạo đề khác
              </Link>
            </div>
          )}
        </div>

        <aside className="page-grid__aside">
          {done ? (
            <section className="sheet sheet--pad quiz-result-aside" aria-live="polite">
              <h2 className="aside-h">Kết quả</h2>
              <div className="quiz-result__summary">
                <p className="quiz-result__score">
                  {session.score != null ? viScore(session.score) : '—'}
                  <span className="quiz-result__of"> / 10</span>
                </p>
                <span className="tag tag--muted">
                  Đúng {correct}/{total}
                </span>
              </div>
              <div className="quiz-result__map">
                {navCells}
              </div>
              {session.feedback ? (
                <p className="quiz-result__fb" style={{ whiteSpace: 'pre-line' }}>
                  {session.feedback}
                </p>
              ) : (
                <p className="field__hint" style={{ margin: 0 }}>
                  Chưa có nhận xét tự động (dịch vụ mô hình ngôn ngữ đang không dùng được).
                </p>
              )}
              {correct < total && (
                <p className="field__hint" style={{ margin: 0 }}>
                  {total - correct} câu sai đã được ghi vào{' '}
                  <Link to="/sinh-vien/on-tap/so-cau-sai">sổ câu sai</Link> — hệ thống sẽ hỏi lại sau 1 ngày.
                </p>
              )}
              <div className="quiz-aside__actions">
                <Link to="/sinh-vien/on-tap" className="btn btn--primary btn--block">
                  Tạo đề khác
                </Link>
                <Link to="/sinh-vien/on-tap" className="btn btn--ghost btn--block">
                  Về trang ôn tập
                </Link>
              </div>
            </section>
          ) : (
            <section className="sheet sheet--pad quiz-aside">
              <h2 className="aside-h">Tiến độ</h2>
              <p className="quiz-aside__count">
                Đã chọn <strong>{answered}</strong>/{total}
              </p>
              <div className="quiz-result__map">
                {navCells}
              </div>
              <button
                type="button"
                className="btn btn--primary btn--block"
                onClick={() => {
                  if (blank > 0) setConfirmEmpty(true);
                  else void onSubmit();
                }}
                disabled={busy}
              >
                {busy ? 'Đang chấm…' : 'Nộp bài'}
              </button>
              {confirmEmpty && (
                <div className="quiz-aside__confirm" role="alert">
                  <p>Còn {blank} câu chưa chọn — vẫn nộp?</p>
                  <div className="row" style={{ gap: 'var(--gap-2)' }}>
                    <button type="button" className="btn btn--ghost btn--sm" onClick={() => setConfirmEmpty(false)}>
                      Làm tiếp
                    </button>
                    <button type="button" className="btn btn--primary btn--sm" onClick={() => void onSubmit()} disabled={busy}>
                      Vẫn nộp
                    </button>
                  </div>
                </div>
              )}
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}

function QuestionCard({
  q,
  done,
  selected,
  onPick,
}: {
  q: QuizQuestion;
  done: boolean;
  selected: number | null;
  onPick: (i: number) => void;
}) {
  const name = `q-${q.id}`;
  return (
    <>
    <fieldset className="quiz-q__set" disabled={done}>
      <legend className="quiz-q__stem">
        <span className="mono quiz-q__n">{q.ordinal}.</span> {q.question}
        {q.fromReview && <span className="tag tag--muted quiz-q__flag">Ôn lại</span>}
      </legend>
      <div className="quiz-q__opts">
        {q.options.map((opt, i) => {
          let state = '';
          if (done && i === q.correctIndex) state = ' quiz-opt--right';
          else if (done && i === selected) state = ' quiz-opt--wrong';
          else if (!done && i === selected) state = ' quiz-opt--on';
          return (
            <label key={i} className={`quiz-opt${state}`}>
              <input type="radio" name={name} checked={selected === i} onChange={() => onPick(i)} />
              <span className="quiz-opt__letter mono">{LETTERS[i]}</span>
              <span className="quiz-opt__text">{opt}</span>
              {done && i === q.correctIndex && (
                <span className="quiz-opt__mark" aria-hidden="true">
                  <Icon name="check" size={16} />
                </span>
              )}
            </label>
          );
        })}
      </div>
    </fieldset>

      {/* Nằm ngoài fieldset: sau khi nộp fieldset bị `disabled`, mọi nút bên trong
          nó (kể cả "Lưu vào sổ tay") cũng bị vô hiệu hóa theo. */}
      {done && (
        <div className="quiz-q__explain">
          {selected === null && <p className="quiz-q__blank">Bạn bỏ trống câu này.</p>}
          <p style={{ margin: 0 }}>{q.explanation}</p>
          {q.sourceFile && (
            <p className="cite__meta" style={{ margin: 0 }}>
              Nguồn: {q.sourceFile}
              {q.sourcePage != null && <>, trang {q.sourcePage}</>}
            </p>
          )}
          <SaveToNotebook onSave={() => learningApi.noteFromQuiz({ sourceId: q.id })} />
        </div>
      )}
    </>
  );
}
