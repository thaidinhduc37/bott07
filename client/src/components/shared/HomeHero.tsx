import { StatTile, type HomeStat } from './StatTile';

export type { HomeStat };

const VN_TZ = 'Asia/Ho_Chi_Minh';

/** "Buổi sáng · Thứ Hai, 24/08/2026" — không trang trí, đây là ngày giờ thật. */
function greetingEyebrow(): string {
  const now = new Date();
  const parts = new Intl.DateTimeFormat('vi-VN', {
    timeZone: VN_TZ,
    weekday: 'long',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(now);

  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  const hour = Number(get('hour'));
  const part = hour < 11 ? 'Buổi sáng' : hour < 13 ? 'Buổi trưa' : hour < 18 ? 'Buổi chiều' : 'Buổi tối';

  return `${part} · ${get('weekday')}, ${get('day')}/${get('month')}/${get('year')}`;
}

/**
 * Đầu trang chủ, dùng chung cho cả ba vai trò.
 *
 * `stats` để `undefined` khi chưa tải xong hoặc trang không có khái niệm
 * "hàng chờ" tự nhiên (quản trị) — không hiện dải rỗng để giữ chỗ.
 */
export function HomeHero({
  name,
  subtitle,
  stats,
}: {
  name: string;
  subtitle?: React.ReactNode;
  stats?: HomeStat[];
}) {
  return (
    <header className="home-hero">
      <p className="eyebrow home-hero__eyebrow">{greetingEyebrow()}</p>
      <h1 className="display home-hero__title">Chào {name}</h1>
      {subtitle && (
        <p className="page-sub" style={{ margin: 'var(--gap-2) 0 0' }}>
          {subtitle}
        </p>
      )}
      {stats && stats.length > 0 && (
        <div className="home-stats">
          {stats.map((s) => (
            <StatTile key={s.label} {...s} />
          ))}
        </div>
      )}
    </header>
  );
}
