import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export interface TrendPoint {
  day: string;
  value: number | null;
}

/**
 * Đường xu hướng theo ngày. `value = null` (vd chưa có tin nhắn nào hôm đó để
 * tính confidence trung bình) bị Recharts tự bỏ điểm đó, không vẽ thành 0.
 */
export function TrendLine({ data, label }: { data: TrendPoint[]; label: string }) {
  if (data.length === 0) {
    return <p style={{ margin: 0, color: 'var(--ink-faint)', fontSize: '0.875rem' }}>Chưa có dữ liệu.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--rule-faint)" vertical={false} />
        <XAxis
          dataKey="day"
          tick={{ fill: 'var(--ink-faint)', fontSize: 11 }}
          axisLine={{ stroke: 'var(--rule-faint)' }}
          tickLine={false}
          minTickGap={24}
        />
        <YAxis tick={{ fill: 'var(--ink-faint)', fontSize: 11 }} axisLine={false} tickLine={false} width={32} />
        <Tooltip
          contentStyle={{
            background: 'var(--sheet)',
            border: '1px solid var(--rule-faint)',
            borderRadius: 8,
            fontSize: 13,
          }}
          labelStyle={{ color: 'var(--ink)' }}
          formatter={(value) => [value, label]}
        />
        <Line type="monotone" dataKey="value" stroke="var(--pen)" strokeWidth={2} dot={false} connectNulls={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
