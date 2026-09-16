import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  STEP_STATUS_TAG,
  approvalsApi,
  type InboxItem,
} from '@/services/approvals-api';
import { viDateTime } from '@/services/forms-api';

export default function ApprovalInboxPage() {
  const [tab, setTab] = useState<'cho' | 'xong'>('cho');
  const [items, setItems] = useState<InboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems((await approvalsApi.inbox(tab === 'xong')).items);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="stack">
      <header>
        <span className="eyebrow">Trình ký</span>
        <h1 className="display page-title">
          Đơn chờ xử lý
        </h1>
        <p className="page-sub">
          Chỉ hiện những đơn đang dừng ở đúng bước bạn phụ trách. Đơn ở cấp khác không xuất hiện ở
          đây, và cũng không xử lý được kể cả khi gõ thẳng đường dẫn.
        </p>
      </header>

      <div className="row" style={{ gap: 'var(--gap-2)' }}>
        <button
          type="button"
          className={`btn ${tab === 'cho' ? 'btn--primary' : 'btn--ghost'}`}
          onClick={() => setTab('cho')}
        >
          Cần xử lý
        </button>
        <button
          type="button"
          className={`btn ${tab === 'xong' ? 'btn--primary' : 'btn--ghost'}`}
          onClick={() => setTab('xong')}
        >
          Đã xử lý
        </button>
      </div>

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <p className="eyebrow">Đang tải…</p>
      ) : items.length === 0 ? (
        <div className="sheet sheet--pad">
          <p style={{ margin: 0, color: 'var(--ink-soft)' }}>
            {tab === 'cho'
              ? 'Không có đơn nào đang chờ bạn. Hết việc.'
              : 'Bạn chưa xử lý đơn nào.'}
          </p>
        </div>
      ) : (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: '1px', background: 'var(--rule-faint)', border: '1px solid var(--rule-faint)' }}>
          {items.map((s) => (
            <li key={s.id} style={{ background: 'var(--sheet)' }}>
              <Link
                to={`/can-bo/don-cho-xu-ly/${s.id}`}
                className="section-card"
                style={{ display: 'block', padding: '1rem 1.15rem', textDecoration: 'none', color: 'inherit' }}
              >
                <div className="spread" style={{ alignItems: 'flex-start', gap: 'var(--gap-4)' }}>
                  <div>
                    <div className="row" style={{ gap: 'var(--gap-3)', alignItems: 'baseline' }}>
                      <span className="mono" style={{ fontSize: '0.8125rem', color: 'var(--seal)' }}>
                        {s.code}
                      </span>
                      <h2 className="display" style={{ fontSize: '1rem', margin: 0 }}>
                        {s.template.name}
                      </h2>
                    </div>
                    <p style={{ margin: '0.25rem 0 0', fontSize: '0.875rem', color: 'var(--ink-soft)' }}>
                      {s.owner.fullName}
                      {s.studentCode && <span className="mono"> · {s.studentCode}</span>}
                    </p>
                    <p style={{ margin: '0.15rem 0 0', fontSize: '0.75rem', color: 'var(--ink-faint)' }}>
                      Gửi {viDateTime(s.submittedAt)}
                      {s.currentStep && ` · đang ở bước ${s.currentStep.stepOrder}: ${s.currentStep.title}`}
                    </p>
                  </div>
                  <span
                    className={`tag ${s.currentStep ? STEP_STATUS_TAG[s.currentStep.status] : 'tag--muted'}`}
                    style={{ flexShrink: 0 }}
                  >
                    {s.statusLabel}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
