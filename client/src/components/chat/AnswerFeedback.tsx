import { useId, useState } from 'react';
import { Icon } from '@/components/shared/Icon';
import { ApiError } from '@/services/api';
import { chatApi, type MessageFeedback } from '@/services/chat-api';

/** Lý do khi chọn "Chưa đúng" — khớp `REASONS` ở backend (`models/feedback.py`). */
const REASONS: { value: string; label: string; onlyAbstained?: boolean }[] = [
  { value: 'WRONG', label: 'Nội dung sai hoặc lỗi thời' },
  { value: 'NO_SOURCE', label: 'Thiếu hoặc sai nguồn trích dẫn' },
  { value: 'IRRELEVANT', label: 'Không đúng câu hỏi' },
  { value: 'SHOULD_ANSWER', label: 'Đáng lẽ trợ lý phải trả lời được', onlyAbstained: true },
  { value: 'OTHER', label: 'Lý do khác' },
];

/**
 * Nút phản hồi dưới mỗi câu trả lời của trợ lý: "Hữu ích" lưu ngay; "Chưa đúng" mở khung chọn lý do
 * (và ghi chú tùy chọn) rồi mới gửi. Bấm lại nút đang chọn thì bỏ đánh giá. Phản hồi giúp cán bộ biết
 * câu nào trợ lý trả lời sai để bổ sung tài liệu — nên cũng áp dụng cho câu trợ lý từ chối (có thể
 * đáng lẽ trả lời được).
 */
export function AnswerFeedback({
  messageId,
  initial,
  abstained,
}: {
  messageId: string;
  initial: MessageFeedback | null | undefined;
  abstained: boolean;
}) {
  const [saved, setSaved] = useState<MessageFeedback | null>(initial ?? null);
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState<string>(initial?.reason ?? '');
  const [comment, setComment] = useState(initial?.comment ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [thanks, setThanks] = useState(false);
  const groupName = useId();

  async function send(body: { rating: 'UP' | 'DOWN' | null; reason?: string; comment?: string }) {
    setBusy(true);
    setError(null);
    try {
      const r = await chatApi.feedback(messageId, body);
      setSaved(r.feedback);
      setAsking(false);
      setThanks(r.feedback !== null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không gửi được phản hồi');
    } finally {
      setBusy(false);
    }
  }

  function onUp() {
    if (saved?.rating === 'UP') void send({ rating: null });
    else void send({ rating: 'UP' });
  }

  function onDown() {
    if (saved?.rating === 'DOWN' && !asking) {
      void send({ rating: null });
      return;
    }
    setAsking((v) => !v);
    setThanks(false);
  }

  const options = REASONS.filter((r) => !r.onlyAbstained || abstained);

  return (
    <div className="fb">
      <div className="fb__row">
        <span className="fb__label" id={`${groupName}-label`}>
          {abstained ? 'Phản hồi về lần từ chối này' : 'Câu trả lời có hữu ích không?'}
        </span>
        <div role="group" aria-labelledby={`${groupName}-label`} className="fb__btns">
          <button
            type="button"
            className="fb__btn"
            aria-pressed={saved?.rating === 'UP'}
            disabled={busy}
            onClick={onUp}
          >
            <Icon name="thumbUp" size={16} />
            Hữu ích
          </button>
          <button
            type="button"
            className="fb__btn"
            aria-pressed={saved?.rating === 'DOWN'}
            aria-expanded={asking}
            disabled={busy}
            onClick={onDown}
          >
            <Icon name="thumbDown" size={16} />
            Chưa đúng
          </button>
        </div>
        {thanks && !asking && (
          <span className="fb__thanks" role="status">
            Cảm ơn bạn đã phản hồi.
          </span>
        )}
      </div>

      {asking && (
        <form
          className="fb__form"
          onSubmit={(e) => {
            e.preventDefault();
            void send({ rating: 'DOWN', reason: reason || undefined, comment: comment.trim() || undefined });
          }}
        >
          <fieldset className="fb__reasons">
            <legend className="fb__legend">Chưa đúng ở điểm nào?</legend>
            {options.map((o) => (
              <label key={o.value} className="fb__reason">
                <input
                  type="radio"
                  name={`${groupName}-reason`}
                  value={o.value}
                  checked={reason === o.value}
                  onChange={() => setReason(o.value)}
                />
                {o.label}
              </label>
            ))}
          </fieldset>
          <div className="field">
            <label className="field__label" htmlFor={`${groupName}-comment`}>
              Ghi chú thêm (không bắt buộc)
            </label>
            <textarea
              id={`${groupName}-comment`}
              className="field__input"
              rows={2}
              maxLength={500}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Ví dụ: Điều 12 đã được sửa đổi năm 2025."
            />
          </div>
          <div className="row" style={{ gap: 'var(--gap-3)' }}>
            <button type="submit" className="btn btn--primary" disabled={busy || !reason}>
              {busy ? 'Đang gửi…' : 'Gửi phản hồi'}
            </button>
            <button type="button" className="btn btn--ghost" disabled={busy} onClick={() => setAsking(false)}>
              Hủy
            </button>
          </div>
          <p className="fb__note">Phản hồi được gửi ẩn danh tới cán bộ phụ trách, không kèm tên của bạn.</p>
        </form>
      )}

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
