import { StatTile } from '@/components/shared/StatTile';
import { TrendLine } from '@/components/shared/charts/TrendLine';
import { DonutBreakdown } from '@/components/shared/charts/DonutBreakdown';
import type { RagAdminStats } from '@/services/admin-api';
import { DashboardSection } from './DashboardSection';
import type { Loaded } from './useDashboardSection';
import { pct } from './format';

/** Tỉ lệ từ chối trả lời của một ngày trong dailyTrend — dùng chung cho cả
 *  sparkline trong StatTile lẫn TrendLine lớn bên dưới, tránh tính hai lần
 *  hai công thức có thể lệch nhau. */
function abstentionRateOf(d: RagAdminStats['dailyTrend'][number]): number | null {
  return d.total === 0 ? null : Math.round((d.abstained / d.total) * 100);
}

/** Tỉ lệ mất căn cứ của một ngày — trên số tin đã trả lời (bỏ tin bị từ
 *  chối), đúng định nghĩa `groundedFailureRate` tổng ở backend. */
function groundedFailureRateOf(d: RagAdminStats['dailyTrend'][number]): number | null {
  const answered = d.total - d.abstained;
  return answered === 0 ? null : Math.round((d.groundedFailures / answered) * 100);
}

export function RagSection({ state }: { state: Loaded<RagAdminStats> }) {

  return (
    <DashboardSection<RagAdminStats>
      title="Chất lượng RAG"
      desc="Tỉ lệ từ chối trả lời và độ tin cậy 30 ngày qua — dấu hiệu cần nạp thêm tài liệu."
      state={state}
    >
      {(data) => (
        <>
          <div className="home-stats" style={{ borderTop: 0, paddingTop: 0, marginTop: 0 }}>
            <StatTile
              value={pct(data.abstentionRate)}
              label="Tỉ lệ từ chối trả lời %"
              tone={pct(data.abstentionRate) > 30 ? 'warn' : 'ok'}
              trend={data.dailyTrend.map((d) => ({ day: d.day, value: abstentionRateOf(d) }))}
            />
            <StatTile
              value={pct(data.groundedFailureRate)}
              label="Tỉ lệ trả lời không có căn cứ %"
              tone={pct(data.groundedFailureRate) > 10 ? 'seal' : 'ok'}
              trend={data.dailyTrend.map((d) => ({ day: d.day, value: groundedFailureRateOf(d) }))}
            />
          </div>

          <TrendLine
            label="Tỉ lệ từ chối trả lời (%)"
            data={data.dailyTrend.map((d) => ({ day: d.day.slice(5), value: abstentionRateOf(d) }))}
          />

          <div>
            <p className="eyebrow" style={{ marginBottom: 'var(--gap-2)' }}>
              Theo chế độ hỏi đáp
            </p>
            <DonutBreakdown
              items={data.byMode.map((m) => ({
                label: m.mode === 'QUYCHE' ? 'Quy chế' : 'Giáo trình',
                count: m.count,
              }))}
            />
          </div>
        </>
      )}
    </DashboardSection>
  );
}
