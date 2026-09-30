import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

export interface Metric {
  label: string;
  /** Con số / chuỗi ngắn hiển thị lớn. */
  value: ReactNode;
  /** Dòng nhỏ dưới số ("điểm TB 7,5", "còn 12 ngày"). */
  hint?: ReactNode;
  /** Có `to` thì cả ô là liên kết. */
  to?: string;
  /** Làm nổi ô cần chú ý (vd câu đến hạn > 0). */
  tone?: 'warn' | 'ok';
}

/**
 * Hàng số liệu đầu trang chủ: 2–4 ô cùng chiều cao, chỉ chữ (không icon trang trí).
 * Dùng chung trang chủ học viên và trang chủ giáo viên / cán bộ để hai bên đọc giống nhau.
 */
export function Metrics({ items, label }: { items: Metric[]; label: string }) {
  return (
    <ul className="metrics" aria-label={label}>
      {items.map((m) => {
        const body = (
          <>
            <span className="metric__label">{m.label}</span>
            <span className={`metric__value${m.tone ? ` metric__value--${m.tone}` : ''}`}>{m.value}</span>
            {m.hint && <span className="metric__hint">{m.hint}</span>}
          </>
        );
        return (
          <li key={m.label} className="metric">
            {m.to ? (
              <Link to={m.to} className="metric__body metric__body--link">
                {body}
              </Link>
            ) : (
              <div className="metric__body">{body}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
