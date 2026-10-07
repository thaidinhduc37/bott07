import { useEffect, useState } from 'react';
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
  // Môn đã có ngân hàng câu hỏi của giảng viên → học viên được chọn nguồn câu hỏi.
  const [bank, setBank] = useState<Record<string, number>>({});
  const [source, setSource] = useState<'ai' | 'bank'>('ai');
  useEffect(() => {
    learningApi
      .bank()
      .then((r) => setBank(Object.fromEntries(r.items.map((i) => [i.courseId, i.count]))))
      .catch(() => setBank({}));
  }, []);
  const bankCount = draft.courseId ? (bank[draft.courseId] ?? 0) : 0;
  const useBank = source === 'bank' && bankCount > 0;
  const ready = useBank || draft.topic.trim().length >= 3;

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    setAbstain(null);
    try {
      const r = await learningApi.createQuiz({
        source: useBank ? 'bank' : 'ai',
        topic: draft.topic.trim() || undefined,
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
    <form className="sheet sheet--pad oh-composer" onSubmit={onCreate}>
      <h2 className="aside-h">Tạo đề mới</h2>
      {bankCount > 0 && (
        <div className="field">
          <span className="field__label" id="on-tap-nguon-label">
            Nguồn câu hỏi
          </span>
          <fieldset
            className="seg"
            style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}
            aria-labelledby="on-tap-nguon-label"
          >
            <legend className="sr-only">Nguồn câu hỏi</legend>
            <label className={`seg__opt${source === 'ai' ? ' seg__opt--on' : ''}`}>
              <input type="radio" name="on-tap-nguon" checked={source === 'ai'} onChange={() => setSource('ai')} />
              Soạn từ giáo trình
            </label>
            <label className={`seg__opt${source === 'bank' ? ' seg__opt--on' : ''}`}>
              <input type="radio" name="on-tap-nguon" checked={source === 'bank'} onChange={() => setSource('bank')} />
              Ngân hàng của giảng viên ({bankCount} câu)
            </label>
          </fieldset>
        </div>
      )}
      <div className="field" hidden={useBank}>
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
      {useBank && (
        <p className="field__hint" style={{ margin: 0 }}>
          Câu hỏi do giảng viên soạn, rút ngẫu nhiên từ ngân hàng của môn này.
        </p>
      )}
      <div className="oh-composer__row">
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
                {bank[c.id] ? ' · có ngân hàng câu hỏi' : ''}
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
              <label key={n} className={`seg__opt${nQuestions === n ? ' seg__opt--on' : ''}`}>
                <input type="radio" name="on-tap-so-cau" checked={nQuestions === n} onChange={() => setNQuestions(n)} />
                {n}
              </label>
            ))}
          </fieldset>
        </div>
        <button type="submit" className="btn btn--primary oh-composer__go" disabled={busy || !ready}>
          {busy ? (useBank ? 'Đang rút câu hỏi…' : 'Đang soạn câu hỏi…') : 'Tạo đề'}
        </button>
      </div>

      {abstain && <div className="notice notice--warn">{abstain}</div>}
      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}
    </form>
  );
}
