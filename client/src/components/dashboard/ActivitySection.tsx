import { StatTile } from '@/components/shared/StatTile';
import { Icon } from '@/components/shared/Icon';
import { StatusBarList } from '@/components/shared/charts/StatusBarList';
import { TrendLine } from '@/components/shared/charts/TrendLine';
import { adminDashboardApi, type ActivityAdminStats } from '@/services/admin-api';
import { DashboardSection } from './DashboardSection';
import { useDashboardSection } from './useDashboardSection';

export function ActivitySection({ refreshKey }: { refreshKey: number }) {
  const state = useDashboardSection(adminDashboardApi.activity, refreshKey);

  return (
    <DashboardSection<ActivityAdminStats>
      title="Hoạt động & lịch học"
      desc="Mức độ dùng hệ thống và dấu hiệu đăng nhập bất thường."
      state={state}
    >
      {(data) => (
        <>
          <div className="home-stats" style={{ borderTop: 0, paddingTop: 0, marginTop: 0 }}>
            <StatTile value={data.activeUsers7d} label="Hoạt động 7 ngày qua" tone="pen" />
            <StatTile value={data.activeUsers30d} label="Hoạt động 30 ngày qua" tone="pen" />
            <StatTile value={data.scheduleThisWeek} label="Buổi học tuần này" tone="pen" />
            <StatTile value={data.examsNext14d} label="Lịch thi 14 ngày tới" tone="pen" />
          </div>

          <StatusBarList
            items={data.usersByRole.map((r) => ({ label: r.role, count: r.count, tone: 'pen' as const }))}
          />

          <div>
            <p className="eyebrow" style={{ marginBottom: 'var(--gap-2)' }}>
              Đăng nhập thất bại theo ngày
            </p>
            {data.failedLogins7d.length === 0 ? (
              <div className="empty">
                <span className="empty__icon" aria-hidden="true">
                  <Icon name="lock" size={22} />
                </span>
                <p className="empty__title">Không có lần đăng nhập thất bại nào trong 7 ngày qua</p>
              </div>
            ) : (
              <TrendLine
                label="Đăng nhập thất bại"
                data={data.failedLogins7d.map((d) => ({ day: d.day.slice(5), value: d.count }))}
              />
            )}
          </div>
        </>
      )}
    </DashboardSection>
  );
}
