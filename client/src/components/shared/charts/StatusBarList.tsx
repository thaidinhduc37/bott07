import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

type Tone = 'pen' | 'ok' | 'warn' | 'seal' | 'muted';

const TONE_VAR: Record<Tone, string> = {
  pen: 'var(--pen)',
  ok: 'var(--ok)',
  warn: 'var(--warn)',
  seal: 'var(--seal)',
  muted: 'var(--ink-faint)',
};

export interface StatusBarItem {
  label: string;
  count: number;
  tone?: Tone;
}

/**
 * Thanh ngang xếp theo giá trị giảm dần — dùng cho mọi phân bố theo nhóm
 * (trạng thái đơn, mẫu đơn, trạng thái chỉ mục, vai trò người dùng). Màu mặc
 * định là mực; người gọi truyền `tone` cho nhãn cần màu ngữ nghĩa riêng.
 */
export function StatusBarList({ items }: { items: StatusBarItem[] }) {
  if (items.length === 0) {
    return <p style={{ margin: 0, color: 'var(--ink-faint)', fontSize: '0.875rem' }}>Chưa có dữ liệu.</p>;
  }

  const sorted = [...items].sort((a, b) => b.count - a.count);
  const height = Math.max(sorted.length * 34, 60);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={sorted} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="label"
          width={140}
          tick={{ fill: 'var(--ink-soft)', fontSize: 12 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          cursor={{ fill: 'var(--sheet-2)' }}
          contentStyle={{
            background: 'var(--sheet)',
            border: '1px solid var(--rule-faint)',
            borderRadius: 8,
            fontSize: 13,
          }}
        />
        <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={16}>
          {sorted.map((item) => (
            <Cell key={item.label} fill={TONE_VAR[item.tone ?? 'pen']} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
