import { useState } from 'react';
import { Icon } from '@/components/shared/Icon';
import { ApiError } from '@/services/api';

/**
 * Nút "Lưu vào sổ tay" dùng chung cho câu trả lời hỏi đáp và câu trắc nghiệm.
 * Backend trả lại ghi chú cũ nếu đã lưu trước đó, nên bấm lại không tạo bản trùng.
 */
export function SaveToNotebook({ onSave }: { onSave: () => Promise<unknown> }) {
  const [state, setState] = useState<'idle' | 'saving' | 'saved'>('idle');
  const [error, setError] = useState<string | null>(null);

  async function save() {
    if (state !== 'idle') return;
    setState('saving');
    setError(null);
    try {
      await onSave();
      setState('saved');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không lưu được vào sổ tay');
      setState('idle');
    }
  }

  return (
    <span className="quiz-save-row">
      {state === 'saved' ? (
        <span className="quiz-save quiz-save--done">
          <Icon name="check" size={14} />
          Đã lưu vào sổ tay
        </span>
      ) : (
        <button type="button" className="btn btn--quiet btn--sm" onClick={() => void save()} disabled={state === 'saving'}>
          {state === 'saving' ? 'Đang lưu…' : 'Lưu vào sổ tay'}
        </button>
      )}
      {error && (
        <span className="quiz-save__error" role="alert">
          {error}
        </span>
      )}
    </span>
  );
}
