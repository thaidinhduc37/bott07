import { Line, LineChart } from 'recharts';

export interface SparklinePoint {
  day: string;
  value: number | null;
}

/**
 * Đường xu hướng nhỏ cạnh một số liệu — trả lời "con số này đang đi lên hay
 * xuống", thứ một con số trần không nói được. Không trục, không nhãn: chỉ
 * hình dạng. Cần ít nhất 2 điểm mới vẽ được một đường có nghĩa.
 */
export function Sparkline({ data }: { data: SparklinePoint[] }) {
  if (data.length < 2) return null;

  return (
    <LineChart width={64} height={28} data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
      <Line
        type="monotone"
        dataKey="value"
        stroke="var(--ink-faint)"
        strokeWidth={1.5}
        dot={false}
        connectNulls={false}
        isAnimationActive={false}
      />
    </LineChart>
  );
}
