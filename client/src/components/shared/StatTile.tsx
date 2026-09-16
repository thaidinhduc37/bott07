import { Sparkline, type SparklinePoint } from './charts/Sparkline';

export interface HomeStat {
  value: number;
  label: string;
  /** Ngữ nghĩa màu dùng lại đúng bảng của `.tag`: hổ phách = cần chú ý, lục =
   *  xong, mực = thông tin mới, đỏ = dè xẻn, chỉ cho trường hợp thật sự cần. */
  tone: 'seal' | 'warn' | 'ok' | 'pen';
  /** Xu hướng theo ngày, vẽ sparkline nhỏ cạnh số. Bỏ trống cho số đếm tức
   *  thời/tương lai không có chuỗi xu hướng tự nhiên (vd "buổi học tuần này"). */
  trend?: SparklinePoint[];
}

/**
 * Một ô số liệu — giá trị lớn + nhãn + chấm màu ngữ nghĩa, kèm sparkline nếu
 * có xu hướng theo ngày. Tách khỏi `HomeHero` để dashboard điều hành và
 * `ServicesPage` dùng lại được, thay vì mỗi nơi tự viết một khối `<dl>` style
 * tay.
 */
export function StatTile({ value, label, tone, trend }: HomeStat) {
  return (
    <div className={`home-stat home-stat--${tone}`}>
      <span className="home-stat__dot" aria-hidden="true" />
      <div>
        <div className="home-stat__value">{value}</div>
        <div className="home-stat__label">{label}</div>
      </div>
      {trend && <Sparkline data={trend} />}
    </div>
  );
}
