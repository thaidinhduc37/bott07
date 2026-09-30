import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  STEP_STATUS_TAG,
  approvalsApi,
  type InboxItem,
} from '@/services/approvals-api';
import { viDateTime } from '@/services/forms-api';
import { PageHeader } from '@/components/shared/PageHeader';

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
      <PageHeader
        eyebrow="Trình ký"
        title="Đơn chờ xử lý"
        description="Danh sách đơn theo trạng thái bạn chọn."
      />

      <div className="page-grid">
        <div className="page-grid__main">
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
            <ul className="appr-list">
              {items.map((s) => (
                <li key={s.id} className="appr-list__item">
                  <Link
                    to={`/can-bo/don-cho-xu-ly/${s.id}`}
                    className="appr-row"
                  >
                    <span className="appr-row__code mono">{s.code}</span>
                    <span className="appr-row__body">
                      <span className="appr-row__title">{s.template.name}</span>
                      <span className="appr-row__meta">
                        {s.owner.fullName}
                        {s.studentCode && <span className="mono"> · {s.studentCode}</span>}
                      </span>
                      <span className="appr-row__sub">
                        Gửi {viDateTime(s.submittedAt)}
                        {s.currentStep && ` · đang ở bước ${s.currentStep.stepOrder}: ${s.currentStep.title}`}
                      </span>
                    </span>
                    <span
                      className={`tag ${s.currentStep ? STEP_STATUS_TAG[s.currentStep.status] : 'tag--muted'}`}
                      style={{ flexShrink: 0 }}
                    >
                      {s.statusLabel}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        <aside className="page-grid__aside">
          <section className="sheet sheet--pad">
            <h2 className="aside-h">Trạng thái</h2>
            <fieldset className="radio-list">
              <legend className="field__hint" style={{ margin: 0 }}>
                Chọn nhóm đơn cần xem
              </legend>
              <label className="radio-row">
                <input
                  type="radio"
                  name="don-trang-thai"
                  checked={tab === 'cho'}
                  onChange={() => setTab('cho')}
                />
                <span className="radio-row__label">Cần xử lý</span>
              </label>
              <label className="radio-row">
                <input
                  type="radio"
                  name="don-trang-thai"
                  checked={tab === 'xong'}
                  onChange={() => setTab('xong')}
                />
                <span className="radio-row__label">Đã xử lý</span>
              </label>
            </fieldset>
          </section>

          <section className="sheet sheet--pad">
            <h2 className="aside-h">Ghi chú</h2>
            <p className="appr-note">
              Chỉ hiện đơn đang ở đúng bước bạn phụ trách. Đơn ở cấp khác không xuất
              hiện ở đây, và cũng không xử lý được kể cả khi gõ thẳng đường dẫn.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}
