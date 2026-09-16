import { Cell, Pie, PieChart, Tooltip } from 'recharts';

const PALETTE = ['var(--pen)', 'var(--ok)', 'var(--warn)', 'var(--seal)', 'var(--ink-faint)'];

export interface BreakdownItem {
  label: string;
  count: number;
}

/**
 * Bánh donut cho phân bố có ít nhóm (2-5) — QUYCHE/GIAOTRINH/KHAC,
 * QUYCHE-mode/GIAOTRINH-mode. Không dùng cho danh sách dài — quá 5 nhóm thì
 * `StatusBarList` đọc được hơn.
 */
export function DonutBreakdown({ items }: { items: BreakdownItem[] }) {
  const total = items.reduce((s, i) => s + i.count, 0);
  if (total === 0) {
    return <p style={{ margin: 0, color: 'var(--ink-faint)', fontSize: '0.875rem' }}>Chưa có dữ liệu.</p>;
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--gap-5)', flexWrap: 'wrap' }}>
      <PieChart width={140} height={140}>
        <Pie data={items} dataKey="count" nameKey="label" innerRadius={40} outerRadius={64} paddingAngle={2}>
          {items.map((item, i) => (
            <Cell key={item.label} fill={PALETTE[i % PALETTE.length]} stroke="var(--sheet)" strokeWidth={2} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            background: 'var(--sheet)',
            border: '1px solid var(--rule-faint)',
            borderRadius: 8,
            fontSize: 13,
          }}
        />
      </PieChart>
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 'var(--gap-2)' }}>
        {items.map((item, i) => (
          <li
            key={item.label}
            style={{ display: 'flex', alignItems: 'center', gap: 'var(--gap-2)', fontSize: '0.8125rem' }}
          >
            <span
              aria-hidden="true"
              style={{
                width: '0.65rem',
                height: '0.65rem',
                borderRadius: '50%',
                background: PALETTE[i % PALETTE.length],
                flex: 'none',
              }}
            />
            <span>{item.label}</span>
            <span className="mono" style={{ color: 'var(--ink-faint)' }}>
              {item.count} ({Math.round((item.count / total) * 100)}%)
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
