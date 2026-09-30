import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError } from '@/services/api';
import type { CourseRef } from '@/services/chat-api';
import { learningApi } from '@/services/learning-api';

export interface QuizDraft {
  topic: string;
  courseId: string;
}

/**
 * Form "Tạo đề mới" dùng chung cho tab Ôn tập. Trạng thái `topic`/`courseId` do
 * trang cha giữ (controlled) để các nút "Tạo đề ôn" ở tab Kế hoạch có thể điền
 * sẵn; `nQuestions`, `busy`, `error`, `abstain` là state nội bộ.
 */
export function QuizComposer(props: {
  courses: CourseRef[];
  draft: QuizDraft;
  onDraftChange: (d: QuizDraft) => void;
  topicInputRef: React.RefObject<HTMLInputElement | null>;
}) {
  const { courses, draft, onDraftChange, topicInputRef } = props;
  const navigate = useNavigate();
  const [nQuestions, setNQuestions] = useState(5);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [abstain, setAbstain] = useState<string | null>(null);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (draft.topic.trim().length < 3 || busy) return;
    setBusy(true);
    setError(null);
    setAbstain(null);
    try {
      const r = await learningApi.createQuiz({
        topic: draft.topic.trim(),
        courseId: draft.courseId || undefined,
        nQuestions,
      });
      if (r.abstained) {
        setAbstain(r.reason ?? 'Không tìm thấy nội dung đủ liên quan trong giáo trình.');
      } else {
        navigate(`/sinh-vien/on-tap/${r.session.id}`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không tạo được đề ôn tập');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="sheet sheet--pad stack" onSubmit={onCreate}>
      <h2 className="display" style={{ fontSize: '1.15rem', margin: 0 }}>
        Tạo đề mới
      </h2>
      <div className="field">
        <label className="field__label" htmlFor="on-tap-chu-de">
          Chủ đề
        </label>
        <input
          id="on-tap-chu-de"
          ref={topicInputRef}
          className="field__input"
          value={draft.topic}
          maxLength={300}
          placeholder="Ví dụ: tấn công từ chối dịch vụ và cách phòng chống"
          onChange={(e) => onDraftChange({ ...draft, topic: e.target.value })}
        />
        <span className="field__hint">Chủ đề càng cụ thể, câu hỏi càng sát giáo trình.</span>
      </div>
      <div className="field-grid">
        <div className="field">
          <label className="field__label" htmlFor="on-tap-mon">
            Môn học
          </label>
          <select
            id="on-tap-mon"
            className="field__input"
            value={draft.courseId}
            onChange={(e) => onDraftChange({ ...draft, courseId: e.target.value })}
          >
            <option value="">Tất cả môn có giáo trình</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} — {c.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <span className="field__label" id="on-tap-so-cau-label">
            Số câu
          </span>
          <fieldset
            className="seg"
            style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}
            aria-labelledby="on-tap-so-cau-label"
          >
            <legend className="sr-only">Số câu</legend>
            {[3, 5, 8, 10].map((n) => (
              <label
                key={n}
                className={`seg__opt${nQuestions === n ? ' seg__opt--on' : ''}`}
              >
                <input
                  type="radio"
                  name="on-tap-so-cau"
                  checked={nQuestions === n}
                  onChange={() => setNQuestions(n)}
                />
                {n}
              </label>
            ))}
          </fieldset>
        </div>
      </div>

      {abstain && <div className="notice notice--warn">{abstain}</div>}
      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      <div className="study-form__actions">
        <button type="submit" className="btn btn--primary" disabled={busy || draft.topic.trim().length < 3}>
          {busy ? 'Đang soạn câu hỏi…' : 'Tạo đề'}
        </button>
      </div>
    </form>
  );
}
