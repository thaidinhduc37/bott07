import { Fragment } from 'react';
import { Link } from 'react-router-dom';

export interface Crumb {
  label: string;
  /** Vắng = mục hiện tại (không phải liên kết). */
  to?: string;
}

/**
 * Đường dẫn quay lại cho trang con ("Ôn tập › Sổ câu sai"). Mục cuối là trang hiện tại,
 * đánh `aria-current="page"`. Dùng qua `PageHeader breadcrumb`.
 */
export function Breadcrumb({ items }: { items: Crumb[] }) {
  return (
    <nav className="crumbs" aria-label="Đường dẫn">
      <ol className="crumbs__list">
        {items.map((c, i) => (
          <Fragment key={`${c.label}-${i}`}>
            <li className="crumbs__item">
              {c.to ? (
                <Link to={c.to} className="crumbs__link">
                  {c.label}
                </Link>
              ) : (
                <span aria-current="page">{c.label}</span>
              )}
            </li>
            {i < items.length - 1 && (
              <li className="crumbs__sep" aria-hidden="true">
                /
              </li>
            )}
          </Fragment>
        ))}
      </ol>
    </nav>
  );
}
