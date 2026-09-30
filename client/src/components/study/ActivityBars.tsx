/**
 * Biểu đồ cột nhỏ: số lượt ôn mỗi ngày. Chỉ để nhìn nhịp học — số chính xác đọc ở
 * `aria-label` của cả biểu đồ và `title` từng cột, nên không cần trục hay chú giải.
 */
export function ActivityBars({ data }: { data: { date: string; count: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  const total = data.reduce((n, d) => n + d.count, 0);
  const label = `${total} lượt ôn trong ${data.length} ngày gần nhất`;
  return (
    <div className="bars" role="img" aria-label={label}>
      {data.map((d, i) => {
        const [, m, day] = d.date.split('-');
        const last = i === data.length - 1;
        return (
          <div key={d.date} className="bars__col" title={`${day}/${m}: ${d.count} lượt`}>
            <span
              className={`bars__bar${d.count === 0 ? ' bars__bar--empty' : ''}${last ? ' bars__bar--today' : ''}`}
              style={{ height: `${d.count === 0 ? 4 : 10 + (d.count / max) * 90}%` }}
            />
            <span className="bars__tick" aria-hidden="true">
              {i % 2 === (data.length - 1) % 2 ? day : ''}
            </span>
          </div>
        );
      })}
    </div>
  );
}
