import { StatusBarList } from '@/components/shared/charts/StatusBarList';
import { Icon } from '@/components/shared/Icon';
import { adminDashboardApi, type DocumentsAdminStats } from '@/services/admin-api';
import { DashboardSection } from './DashboardSection';
import { useDashboardSection } from './useDashboardSection';
import { INDEX_STATUS_LABEL, toneFor } from './format';

export function DocumentsSection({ refreshKey }: { refreshKey: number }) {
  const state = useDashboardSection(adminDashboardApi.documents, refreshKey);

  return (
    <DashboardSection<DocumentsAdminStats>
      title="Tài liệu & chỉ mục"
      desc="Tài liệu nào lập chỉ mục lỗi và cần xử lý thủ công."
      state={state}
    >
      {(data) => (
        <>
          <StatusBarList
            items={Object.entries(data.byIndexStatus).map(([status, v]) => ({
              label: INDEX_STATUS_LABEL[status] ?? status,
              count: v.versions,
              tone: toneFor(status),
            }))}
          />

          <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--ink-soft)' }}>
            Đồng bộ với Qdrant:{' '}
            <span className={`tag ${data.ragConsistency === 'in_sync' ? 'tag--ok' : 'tag--warn'}`}>
              {data.ragConsistency === 'in_sync' ? 'khớp' : data.ragConsistency}
            </span>
          </p>

          {data.failedList.length === 0 ? (
            <div className="empty">
              <span className="empty__icon" aria-hidden="true">
                <Icon name="check" size={22} />
              </span>
              <p className="empty__title">Không có tài liệu nào lỗi lập chỉ mục</p>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Tài liệu</th>
                    <th className="num">Phiên bản</th>
                    <th>Lỗi</th>
                  </tr>
                </thead>
                <tbody>
                  {data.failedList.map((f) => (
                    <tr key={`${f.documentTitle}-${f.version}`}>
                      <td>{f.documentTitle}</td>
                      <td className="num mono">{f.version}</td>
                      <td style={{ color: 'var(--seal-ink)' }}>{f.indexError ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </DashboardSection>
  );
}
