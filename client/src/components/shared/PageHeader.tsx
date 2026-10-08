import type { ReactNode } from 'react';
import { Breadcrumb, type Crumb } from './Breadcrumb';

/**
 * Phần đầu trang dùng chung: nhãn nhỏ · tiêu đề · mô tả · nút hành động · tab. Không tự cộng khoảng cách: khoảng tới nội dung là của
 * `.stack` cha (24px), hoặc 20px khi có tab để tab dính sát nội dung nó điều khiển. Có `tabs` thì header gọn lại (mô tả nhỏ hơn,
 * tab nằm sát đáy với đường kẻ chung).
 *
 * ```tsx
 * <PageHeader eyebrow="Hành chính" title="Đơn của tôi" actions={<Link …>Tạo đơn mới</Link>} />
 * <PageHeader title="Ôn tập" description="…" tabs={<Tabs … />} />
 * ```
 */
export function PageHeader({
  title,
  description,
  eyebrow,
  breadcrumb,
  actions,
  tabs,
}: {
  title: ReactNode;
  /** Một câu ngắn. Đoạn dài hơn nên để ở khối "Lưu ý" trong trang, không ở đầu trang. */
  description?: ReactNode;
  /** Nhãn nhỏ phía trên tiêu đề ("Hành chính", "Ôn tập · CS304"). */
  eyebrow?: ReactNode;
  /** Trang con: đường dẫn quay về trang cha, nằm trên cùng phần đầu trang. */
  breadcrumb?: Crumb[];
  /** Nút / liên kết hành động chính, nằm bên phải hàng tiêu đề. */
  actions?: ReactNode;
  /** Thường là `<Tabs />`. */
  tabs?: ReactNode;
}) {
  return (
    <header className={`page-head${tabs ? ' page-head--tabs' : ''}`}>
      {breadcrumb && <Breadcrumb items={breadcrumb} />}
      <div className="page-head__row">
        <div className="page-head__text">
          {eyebrow && <span className="eyebrow page-head__eyebrow">{eyebrow}</span>}
          <h1 className="display page-title">{title}</h1>
          {description && <p className="page-sub">{description}</p>}
        </div>
        {actions && <div className="page-head__actions">{actions}</div>}
      </div>
      {tabs}
    </header>
  );
}
