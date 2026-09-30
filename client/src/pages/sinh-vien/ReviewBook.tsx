import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Icon } from '@/components/shared/Icon';
import { PageHeader } from '@/components/shared/PageHeader';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { ApiError } from '@/services/api';
import { learningApi, type ReviewItem, type ReviewOverview } from '@/services/learning-api';

const LETTERS = ['A', 'B', 'C', 'D'];
const DAY = new Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium' });

type Filter = 'due' | 'learning' | 'mastered' | 'all';

function matches(item: ReviewItem, f: Filter): boolean {
  if (f === 'all') return true;
  if (f === 'due') return item.isDue;
  if (f === 'mastered') return item.mastered;
  return !item.mastered && !item.isDue;
}

function dueLabel(item: ReviewItem): { text: string; tone: string } {
  if (item.mastered) return { text: 'Đã thuộc', tone: 'tag--ok' };
  if (item.isDue) return { text: 'Đến hạn ôn', tone: 'tag--warn' };
  return { text: `Ôn lại ${DAY.format(new Date(item.dueAt!))}`, tone: 'tag--muted' };
}

/** Sổ câu sai: mọi câu từng làm sai, kèm đáp án đúng, nguồn và hẹn ôn lại. */
export default function ReviewBookPage() {
  useDocumentTitle('Sổ câu sai');
  const navigate = useNavigate();
  const [data, setData] = useState<ReviewOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<Filter>('all');
  const [confirmId, setConfirmId] = useState<string | null>(null);

  function load() {
    learningApi
      .reviewItems()
      .then(setData)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Không tải được sổ câu sai'));
  }
  useEffect(load, []);

  async function onReview() {
    setBusy(true);
    setError(null);
    try {
      const s = await learningApi.createReview();
      navigate(`/sinh-vien/on-tap/${s.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không tạo được lượt ôn');
      setBusy(false);
    }
  }

  async function onRemove(item: ReviewItem) {
    setConfirmId(null);
    try {
      await learningApi.removeReviewItem(item.id);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không xóa được');
    }
  }

  const items = data ? data.items.filter((i) => matches(i, filter)) : [];

  const counts: Record<Filter, number> = data
    ? {
        all: data.items.length,
        due: data.due,
        learning: data.learning,
        mastered: data.mastered,
      }
    : { all: 0, due: 0, learning: 0, mastered: 0 };

  return (
    <div className="stack">
      <PageHeader
        breadcrumb={[{ label: 'Ôn tập', to: '/sinh-vien/on-tap' }, { label: 'Sổ câu sai' }]}
        title="Sổ câu sai"
      />

      <div className="page-grid">
        <div className="page-grid__main">
          {error && (
            <div className="notice notice--error" role="alert">
              {error}
            </div>
          )}

          {!data ? (
            !error && <p className="eyebrow">Đang tải…</p>
          ) : data.items.length === 0 ? (
            <div className="empty">
              <span className="empty__icon" aria-hidden="true">
                <Icon name="check" size={22} />
              </span>
              <p className="empty__title">Sổ đang trống</p>
              <p>Câu nào bạn làm sai khi ôn tập sẽ được ghi vào đây.</p>
            </div>
          ) : (
            <>
              {items.length === 0 ? (
                <p className="field__hint">Không có câu nào ở nhóm này.</p>
              ) : (
            <div className="sheet review-list">
              {items.map((item) => {
                const due = dueLabel(item);
                return (
                  <div key={item.id} className="review-item">
                    <div className="review-item__top">
                      <p className="review-item__q">{item.question}</p>
                      {confirmId === item.id ? (
                        <span className="review-item__confirm">
                          <span>Xóa?</span>
                          <button
                            type="button"
                            className="btn btn--danger btn--sm"
                            onClick={() => void onRemove(item)}
                          >
                            Có
                          </button>
                          <button
                            type="button"
                            className="btn btn--ghost btn--sm"
                            onClick={() => setConfirmId(null)}
                          >
                            Không
                          </button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="btn btn--quiet btn--icon"
                          aria-label="Xóa khỏi sổ"
                          title="Xóa khỏi sổ"
                          onClick={() => setConfirmId(item.id)}
                        >
                          <Icon name="trash" size={16} />
                        </button>
                      )}
                    </div>
                    <p className="review-item__ans">
                      <strong>Đáp án:</strong> {LETTERS[item.correctIndex]}.{' '}
                      {item.options[item.correctIndex]}
                    </p>
                    <details className="review-item__ex">
                      <summary>Xem giải thích</summary>
                      <p>{item.explanation}</p>
                    </details>
                    <div className="review-item__meta">
                      <span className={`tag ${due.tone}`}>{due.text}</span>
                      {item.course && <span className="tag tag--muted mono">{item.course.code}</span>}
                      <span className="tag tag--muted">Sai {item.timesWrong} lần</span>
                      {item.sourceFile && (
                        <span className="cite__meta">
                          {item.sourceFile}
                          {item.sourcePage != null && <>, tr. {item.sourcePage}</>}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
              </div>
            )}
            </>
          )}
        </div>

        <aside className="page-grid__aside">
          {data && (
            <section className="sheet sheet--pad review-aside">
              <h2 className="aside-h">Tóm tắt</h2>
              <dl className="review-aside__stats">
                <div className="review-aside__row">
                  <dt>Đến hạn hôm nay</dt>
                  <dd>{data.due}</dd>
                </div>
                <div className="review-aside__row">
                  <dt>Đang học</dt>
                  <dd>{data.learning}</dd>
                </div>
                <div className="review-aside__row">
                  <dt>Đã thuộc</dt>
                  <dd>{data.mastered}</dd>
                </div>
              </dl>

              <fieldset className="review-aside__filters">
                <legend className="aside-h">Lọc câu</legend>
                {(
                  [
                    ['all', 'Tất cả'],
                    ['due', 'Đến hạn'],
                    ['learning', 'Đang học'],
                    ['mastered', 'Đã thuộc'],
                  ] as const
                ).map(([value, label]) => (
                  <label key={value} className="radio-row">
                    <input
                      type="radio"
                      name="review-filter"
                      checked={filter === value}
                      onChange={() => setFilter(value)}
                    />
                    <span className="radio-row__label">{label}</span>
                    <span className="radio-row__count">{counts[value]}</span>
                  </label>
                ))}
              </fieldset>

              {data.due > 0 && (
                <button type="button" className="btn btn--primary btn--block" onClick={onReview} disabled={busy}>
                  Ôn {data.due} câu đến hạn
                </button>
              )}
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
