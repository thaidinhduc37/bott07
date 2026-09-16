import { StatTile } from '@/components/shared/StatTile';
import { Icon } from '@/components/shared/Icon';
import { StatusBarList } from '@/components/shared/charts/StatusBarList';
import { adminDashboardApi, type FormsAdminStats } from '@/services/admin-api';
import { DashboardSection } from './DashboardSection';
import { useDashboardSection } from './useDashboardSection';
import { STATUS_LABEL, pct, toneFor } from './format';

export function FormsSection({ refreshKey }: { refreshKey: number }) {
  const state = useDashboardSection(adminDashboardApi.forms, refreshKey);

  return (
    <DashboardSection<FormsAdminStats>
      title="Đơn từ & phê duyệt"
      desc="Đơn nào đang tồn đọng, mẫu nào được dùng nhiều nhất, tốc độ xử lý 30 ngày qua."
      state={state}
    >
      {(data) => (
        <>
          <div className="home-stats" style={{ borderTop: 0, paddingTop: 0, marginTop: 0 }}>
            <StatTile
              value={data.avgTurnaroundDays === null ? 0 : Math.round(data.avgTurnaroundDays * 10) / 10}
              label="Ngày xử lý trung bình"
              tone="pen"
              trend={data.avgTurnaroundTrend}
            />
            <StatTile
              value={pct(data.rejectionRate30d)}
              label="Tỉ lệ từ chối % (30 ngày)"
              tone={pct(data.rejectionRate30d) > 20 ? 'warn' : 'ok'}
              trend={data.rejectionRateTrend}
            />
          </div>

          <StatusBarList
            items={data.byStatus.map((s) => ({
              label: STATUS_LABEL[s.status] ?? s.status,
              count: s.count,
              tone: toneFor(s.status),
            }))}
          />

          {data.backlog.length === 0 ? (
            <div className="empty">
              <span className="empty__icon" aria-hidden="true">
                <Icon name="check" size={22} />
              </span>
              <p className="empty__title">Không có đơn nào đang chờ xử lý</p>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Mã đơn</th>
                    <th>Mẫu đơn</th>
                    <th>Trạng thái</th>
                    <th className="num">Chờ (ngày)</th>
                  </tr>
                </thead>
                <tbody>
                  {data.backlog.map((b) => (
                    <tr key={b.code}>
                      <td className="mono">{b.code}</td>
                      <td>{b.templateName}</td>
                      <td>{STATUS_LABEL[b.status] ?? b.status}</td>
                      <td className="num mono">{b.daysWaiting}</td>
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
