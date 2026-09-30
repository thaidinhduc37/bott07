import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Icon } from '@/components/shared/Icon';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { ApiError } from '@/services/api';
import { chatApi, type CourseRef } from '@/services/chat-api';
import { learningApi, type StudyNote } from '@/services/learning-api';
import { PageHeader } from '@/components/shared/PageHeader';

const UPDATED = new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });

const SOURCE_LABEL: Record<StudyNote['sourceType'], string> = {
  CHAT: 'Hỏi đáp',
  QUIZ: 'Trắc nghiệm',
  MANUAL: 'Tự viết',
};

type SourceFilter = 'all' | StudyNote['sourceType'];

/** Sổ tay: câu trả lời, câu hỏi và ghi chú đã lưu từ hỏi đáp, trắc nghiệm hoặc tự viết. */
export default function NotebookPage() {
  useDocumentTitle('Sổ tay');
  const [courses, setCourses] = useState<CourseRef[]>([]);
  const [q, setQ] = useState('');
  const [courseId, setCourseId] = useState('');
  const [source, setSource] = useState<SourceFilter>('all');
  const [items, setItems] = useState<StudyNote[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [formTitle, setFormTitle] = useState('');
  const [formContent, setFormContent] = useState('');
  const [formCourse, setFormCourse] = useState('');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Lọc nguồn phía client trên `items` (tìm kiếm + môn vẫn gọi API như trước).
  const visible = useMemo(
    () => (items ? items.filter((n) => source === 'all' || n.sourceType === source) : null),
    [items, source],
  );

  const sourceCounts: Record<SourceFilter, number> = useMemo(() => {
    const c: Record<SourceFilter, number> = { all: 0, CHAT: 0, QUIZ: 0, MANUAL: 0 };
    for (const n of items ?? []) {
      c.all += 1;
      c[n.sourceType] += 1;
    }
    return c;
  }, [items]);

  function load(query = q, course = courseId) {
    learningApi
      .notes({ q: query.trim() || undefined, courseId: course || undefined })
      .then((r) => setItems(r.items))
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Không tải được sổ tay'));
  }

  useEffect(() => {
    void chatApi.courses().then((r) => setCourses(r.items)).catch(() => setCourses([]));
  }, []);

  // Tìm kiếm debounce 300ms.
  useEffect(() => {
    const t = window.setTimeout(() => load(q, courseId), 300);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, courseId]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (saving || formTitle.trim().length < 2 || formContent.trim().length < 2) return;
    setSaving(true);
    setFormError(null);
    try {
      await learningApi.createNote({
        title: formTitle.trim(),
        content: formContent.trim(),
        courseId: formCourse || courseId || undefined,
      });
      setFormTitle('');
      setFormContent('');
      setFormCourse('');
      setShowForm(false);
      load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Không tạo được ghi chú');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="stack">
      <PageHeader title="Sổ tay" description="Câu trả lời, câu hỏi và ghi chú bạn đã lưu." />

      <div className="page-grid">
        <div className="page-grid__main">
          {showForm && (
            <form className="sheet sheet--pad stack note-form" onSubmit={onCreate}>
              <h2 className="display" style={{ fontSize: '1.15rem', margin: 0 }}>
                Ghi chú mới
              </h2>
              <div className="field">
                <label className="field__label" htmlFor="so-tay-tieu-de">
                  Tiêu đề
                </label>
                <input
                  id="so-tay-tieu-de"
                  className="field__input"
                  value={formTitle}
                  maxLength={200}
                  onChange={(e) => setFormTitle(e.target.value)}
                />
              </div>
              <div className="field">
                <label className="field__label" htmlFor="so-tay-noi-dung">
                  Nội dung
                </label>
                <textarea
                  id="so-tay-noi-dung"
                  className="field__input"
                  value={formContent}
                  onChange={(e) => setFormContent(e.target.value)}
                />
              </div>
              <div className="field">
                <label className="field__label" htmlFor="so-tay-mon-moi">
                  Môn học
                </label>
                <select
                  id="so-tay-mon-moi"
                  className="field__input"
                  value={formCourse}
                  onChange={(e) => setFormCourse(e.target.value)}
                >
                  <option value="">Không gắn môn</option>
                  {courses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.code} — {c.name}
                    </option>
                  ))}
                </select>
              </div>
              {formError && (
                <div className="notice notice--error" role="alert">
                  {formError}
                </div>
              )}
              <div className="row" style={{ gap: 'var(--gap-2)' }}>
                <button type="submit" className="btn btn--primary" disabled={saving || formTitle.trim().length < 2 || formContent.trim().length < 2}>
                  {saving ? 'Đang lưu…' : 'Lưu'}
                </button>
                <button type="button" className="btn btn--ghost" onClick={() => setShowForm(false)}>
                  Hủy
                </button>
              </div>
            </form>
          )}

          {error && (
            <div className="notice notice--error" role="alert">
              {error}
            </div>
          )}

          {!items ? (
            !error && <p className="eyebrow">Đang tải…</p>
          ) : items.length === 0 ? (
            <div className="empty">
              <span className="empty__icon" aria-hidden="true">
                <Icon name="pencil" size={22} />
              </span>
              <p className="empty__title">Sổ tay đang trống</p>
              <p>Bấm "Lưu vào sổ tay" dưới câu trả lời hỏi đáp hoặc câu trắc nghiệm.</p>
            </div>
          ) : (visible?.length ?? 0) === 0 ? (
            <p className="field__hint">Không có ghi chú nào ở nguồn này.</p>
          ) : (
            <div className="sheet note-list">
              {visible!.map((n) => (
                <NoteItem key={n.id} note={n} onChanged={() => load()} />
              ))}
            </div>
          )}
        </div>

        <aside className="page-grid__aside">
          <section className="sheet sheet--pad note-aside">
            <div className="field">
              <label className="sr-only" htmlFor="so-tay-tim">
                Tìm trong sổ tay
              </label>
              <input
                id="so-tay-tim"
                className="field__input"
                value={q}
                placeholder="Tìm theo tiêu đề hoặc nội dung"
                onChange={(e) => setQ(e.target.value)}
              />
            </div>
            <div className="field">
              <label className="sr-only" htmlFor="so-tay-mon">
                Lọc theo môn
              </label>
              <select id="so-tay-mon" className="field__input" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
                <option value="">Tất cả môn</option>
                {courses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code} — {c.name}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              className="btn btn--primary btn--block"
              onClick={() => setShowForm((v) => !v)}
              aria-expanded={showForm}
            >
              <Icon name="plus" size={16} />
              Ghi chú mới
            </button>

            <fieldset className="radio-list">
              <legend className="aside-h">Nguồn</legend>
              {(
                [
                  ['all', 'Tất cả'],
                  ['CHAT', 'Hỏi đáp'],
                  ['QUIZ', 'Trắc nghiệm'],
                  ['MANUAL', 'Tự viết'],
                ] as const
              ).map(([value, label]) => (
                <label key={value} className="radio-row">
                  <input
                    type="radio"
                    name="so-tay-nguon"
                    checked={source === value}
                    onChange={() => setSource(value)}
                  />
                  <span className="radio-row__label">{label}</span>
                  <span className="radio-row__count">{sourceCounts[value]}</span>
                </label>
              ))}
            </fieldset>
          </section>
        </aside>
      </div>
    </div>
  );
}

function NoteItem({ note, onChanged }: { note: StudyNote; onChanged: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [pinned, setPinned] = useState(note.pinned);
  const [pinBusy, setPinBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [saveBusy, setSaveBusy] = useState(false);

  // Đo tràn thật thay vì đoán theo độ dài chuỗi: 5 dòng ngắn vẫn có thể vượt 4 dòng,
  // còn 200 ký tự trên màn rộng có khi chỉ 2 dòng.
  const contentRef = useRef<HTMLParagraphElement>(null);
  const [overflows, setOverflows] = useState(false);
  useLayoutEffect(() => {
    const el = contentRef.current;
    if (el && !expanded) setOverflows(el.scrollHeight > el.clientHeight + 1);
  }, [note.content, expanded]);
  const clamped = !expanded;

  async function onPin() {
    if (pinBusy) return;
    setPinBusy(true);
    setError(null);
    try {
      const r = await learningApi.updateNote(note.id, { pinned: !pinned });
      setPinned(r.pinned);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không ghim được');
    } finally {
      setPinBusy(false);
    }
  }

  async function onRemove() {
    if (removing) return;
    setRemoving(true);
    setError(null);
    try {
      await learningApi.removeNote(note.id);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không xóa được');
      setRemoving(false);
      setConfirming(false);
    }
  }

  async function onSaveNote() {
    if (saveBusy) return;
    setSaveBusy(true);
    setError(null);
    try {
      await learningApi.updateNote(note.id, { note: draft.trim() || null });
      setEditing(false);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không lưu được ghi chú');
    } finally {
      setSaveBusy(false);
    }
  }

  return (
    <div className="note-item">
      <div className="note-item__top">
        <span className="note-item__label">
          {SOURCE_LABEL[note.sourceType]}
          {note.course && (
            <>
              {' · '}
              <span className="mono">{note.course.code}</span>
            </>
          )}
          {' · '}
          Cập nhật {UPDATED.format(new Date(note.updatedAt))}
          {pinned && (
            <span className="note-item__pin" title="Đã ghim" aria-label="Đã ghim">
              <Icon name="pin" size={13} />
            </span>
          )}
        </span>
        <span className="note-item__actions">
          {confirming ? (
            <span className="note-item__confirm">
              <span>Xóa?</span>
              <button type="button" className="btn btn--danger btn--sm" onClick={() => void onRemove()} disabled={removing}>
                {removing ? 'Đang xóa…' : 'Có'}
              </button>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setConfirming(false)}>
                Không
              </button>
            </span>
          ) : (
            <>
              <button
                type="button"
                className="btn btn--quiet btn--sm"
                onClick={() => void onPin()}
                disabled={pinBusy}
              >
                {pinned ? 'Bỏ ghim' : 'Ghim'}
              </button>
              <button type="button" className="btn btn--quiet btn--sm" onClick={() => setConfirming(true)}>
                Xóa
              </button>
            </>
          )}
        </span>
      </div>

      <p className="note-item__title">{note.title}</p>
      <p
        ref={contentRef}
        className={`note-item__content${clamped ? ' note-item__content--clamped' : ''}`}
        style={{ whiteSpace: 'pre-line' }}
      >
        {note.content}
      </p>
      {note.citations.length > 0 && (
        <ul className="note-item__cites">
          {note.citations.map((c) => (
            <li key={c.marker} className="cite__meta">
              <span className="mono">[{c.marker}]</span> {c.documentTitle ?? c.sourceFile ?? 'Tài liệu'}
              {c.page != null && <>, tr. {c.page}</>}
            </li>
          ))}
        </ul>
      )}

      {note.note && !editing && (
        <p className="note-item__own">
          <strong>Ghi chú riêng:</strong> {note.note}
        </p>
      )}
      {editing && (
        <div className="note-item__edit">
          <textarea
            className="field__input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ghi chú riêng của bạn"
          />
          <div className="row" style={{ gap: 'var(--gap-2)' }}>
            <button type="button" className="btn btn--primary btn--sm" onClick={() => void onSaveNote()} disabled={saveBusy}>
              {saveBusy ? 'Đang lưu…' : 'Lưu'}
            </button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditing(false)}>
              Hủy
            </button>
          </div>
        </div>
      )}

      {/* Hàng hành động đặt cuối mục, sau trích dẫn và ghi chú riêng — đúng thứ tự
          đọc. Nút "Xem thêm" nằm ngoài đoạn bị cắt dòng, nằm trong thì nó bị cắt mất. */}
      {(overflows || expanded) || !editing ? (
        <div className="note-item__foot">
          {(overflows || expanded) && (
            <button type="button" className="btn btn--quiet btn--sm" onClick={() => setExpanded(!expanded)}>
              {expanded ? 'Thu gọn' : 'Xem thêm'}
            </button>
          )}
          {!editing && (
            <button
              type="button"
              className="btn btn--quiet btn--sm"
              onClick={() => {
                setDraft(note.note ?? '');
                setEditing(true);
              }}
            >
              <Icon name="pencil" size={14} />
              Sửa ghi chú
            </button>
          )}
        </div>
      ) : null}


      {error && (
        <p className="note-item__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
