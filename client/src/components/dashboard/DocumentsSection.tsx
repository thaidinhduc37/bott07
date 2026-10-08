import { Link } from 'react-router-dom';
import { StatusBarList } from '@/components/shared/charts/StatusBarList';
import { Icon } from '@/components/shared/Icon';
import type { DocumentsAdminStats } from '@/services/admin-api';
import { DashboardSection } from './DashboardSection';
import type { Loaded } from './useDashboardSection';
import { INDEX_STATUS_LABEL, toneFor } from './format';

const DOC_TYPE_LABEL: Record<DocumentsAdminStats['byType'][number]['documentType'], string> = {
  QUYCHE: 'Quy chế',
  GIAOTRINH: 'Giáo trình',
  KHAC: 'Khác',
};

export function DocumentsSection({ state }: { state: Loaded<DocumentsAdminStats> }) {

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
            Đồng bộ với Chroma:{' '}
            <span className={`tag ${data.ragConsistency === 'in_sync' ? 'tag--ok' : 'tag--warn'}`}>
              {data.ragConsistency === 'in_sync' ? 'khớp' : data.ragConsistency}
            </span>
          </p>

          <div>
            <p className="eyebrow" style={{ marginBottom: 'var(--gap-2)' }}>
              Theo loại tài liệu
            </p>
            <StatusBarList
              items={data.byType.map((t) => ({
                label: DOC_TYPE_LABEL[t.documentType] ?? t.documentType,
                count: t.count,
                tone: 'pen' as const,
              }))}
            />
          </div>

          <p style={{ margin: 0 }}>
            <Link className="btn btn--quiet" to="/quan-tri/tai-lieu">
              Quản lý tài liệu
            </Link>
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
