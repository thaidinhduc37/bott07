import { useCallback, useEffect, useState } from 'react';
import { adminApi, type AuditLogEntry } from '@/services/admin-api';
import { viDateTime } from '@/services/forms-api';
import { PageHeader } from '@/components/shared/PageHeader';

/** Nhóm hành động để lọc nhanh, thay vì bắt người dùng nhớ mã hành động. */
const ACTION_GROUPS: Array<{ label: string; value: string }> = [
  { label: 'Tất cả', value: '' },
  { label: 'Đăng nhập', value: 'LOGIN' },
  { label: 'Đăng nhập thất bại', value: 'LOGIN_FAILED' },
  { label: 'Đổi mật khẩu', value: 'PASSWORD_CHANGE' },
  { label: 'Tải tài liệu lên', value: 'DOCUMENT_UPLOAD' },
  { label: 'Xóa tài liệu', value: 'DOCUMENT_DELETE' },
  { label: 'Ký đơn', value: 'FORM_SIGN' },
  { label: 'Ký đơn thất bại', value: 'FORM_SIGN_FAILED' },
  { label: 'Phê duyệt', value: 'FORM_APPROVE' },
  { label: 'Đổi vai trò', value: 'USER_ROLES_UPDATE' },
  { label: 'Đổi trạng thái tài khoản', value: 'USER_STATUS_UPDATE' },
];

export default function AuditLogPage() {
  const [items, setItems] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [action, setAction] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.auditLogs({ page, action: action || undefined });
      setItems(r.items);
      setTotal(r.total);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [page, action]);

  useEffect(() => {
    void load();
  }, [load]);

  const pageSize = 30;
  const pages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Kiểm soát"
        title="Nhật ký thao tác"
        description="Ai làm gì, lúc nào, từ địa chỉ nào."
      />

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <p className="eyebrow">Đang tải…</p>
      ) : items.length === 0 ? (
        <div className="sheet sheet--pad">
          <p style={{ margin: 0, color: 'var(--ink-soft)' }}>Không có bản ghi nào khớp bộ lọc.</p>
        </div>
      ) : (
        <>
          <div className="audit-toolbar">
            <label className="audit-toolbar__filter">
              <span className="field__label">Lọc theo hành động</span>
              <select
                className="field__input"
                value={action}
                onChange={(e) => {
                  setAction(e.target.value);
                  setPage(1);
                }}
              >
                {ACTION_GROUPS.map((g) => (
                  <option key={g.value} value={g.value}>
                    {g.label}
                  </option>
                ))}
              </select>
            </label>
            <span className="audit-toolbar__count">{total} bản ghi</span>
            <div className="audit-toolbar__pages">
              <button type="button" className="btn btn--ghost btn--sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Trang trước
              </button>
              <span className="mono" style={{ fontSize: '0.8125rem', color: 'var(--ink-soft)' }}>
                {page} / {pages}
              </span>
              <button type="button" className="btn btn--ghost btn--sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
                Trang sau
              </button>
            </div>
          </div>
          <p className="field__hint">
            Bao gồm cả các lần đăng nhập và ký đơn thất bại — một nhật ký chỉ ghi việc thành công
            thì không phát hiện được ai đang dò mật khẩu.
          </p>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Thời điểm</th>
                  <th>Người thực hiện</th>
                  <th>Hành động</th>
                  <th>Đối tượng</th>
                  <th>Địa chỉ</th>
                </tr>
              </thead>
              <tbody>
                {items.map((l) => (
                  <tr key={l.id}>
                    <td className="mono" style={{ whiteSpace: 'nowrap', color: 'var(--ink-soft)' }}>
                      {viDateTime(l.createdAt)}
                    </td>
                    <td>
                      {l.user ? (
                        <>
                          {l.user.fullName}
                          <span className="mono" style={{ display: 'block', fontSize: '0.6875rem', color: 'var(--ink-faint)' }}>
                            {l.user.email}
                          </span>
                        </>
                      ) : (
                        <span style={{ color: 'var(--ink-faint)' }}>— (chưa xác định)</span>
                      )}
                    </td>
                    <td className="mono">
                      <span className={l.action.includes('FAILED') ? 'tag tag--seal' : ''}>{l.action}</span>
                    </td>
                    <td className="mono" style={{ fontSize: '0.6875rem', color: 'var(--ink-faint)' }}>
                      {l.entityType ?? '—'}
                      {l.entityId && <span style={{ display: 'block' }}>{l.entityId.slice(0, 8)}…</span>}
                    </td>
                    <td className="mono" style={{ color: 'var(--ink-soft)' }}>
                      {l.ipAddress ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="row" style={{ justifyContent: 'space-between' }}>
            <button type="button" className="btn btn--ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              ← Trang trước
            </button>
            <span className="mono" style={{ fontSize: '0.8125rem', color: 'var(--ink-soft)', alignSelf: 'center' }}>
              {page} / {pages}
            </span>
            <button type="button" className="btn btn--ghost" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
              Trang sau →
            </button>
          </div>
        </>
      )}
    </div>
  );
}
