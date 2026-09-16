import { Link } from 'react-router-dom';
import { Icon, type IconName } from './Icon';

export interface SectionCardProps {
  href?: string;
  icon: IconName;
  title: string;
  description: string;
  /** Chưa mở thì nói thẳng, không dẫn người dùng tới một trang trống. */
  pending?: string;
}

/**
 * Thẻ dẫn tới một khu vực chức năng, dùng ở ba trang chủ.
 *
 * Bỏ `eyebrow`.
 *
 * Bản trước bắt mỗi thẻ mang một nhãn viết hoa phía trên tiêu đề — "Quy chế",
 * "Học vụ", "Hành chính". Bốn thẻ cạnh nhau thành bốn nhãn hoa giãn chữ trên
 * cùng một màn hình, và không nhãn nào giúp phân biệt được gì: người dùng đã
 * đọc tiêu đề "Lịch học và lịch thi" rồi thì "Học vụ" không thêm thông tin. Nó
 * chỉ thêm một dòng chữ dày.
 *
 * Thay bằng **biểu tượng** — cùng bộ với biểu tượng của mục đó trong thanh bên,
 * nên thẻ ở trang chủ và mục ở menu nhận ra nhau. Đó là việc mà nhãn chữ không
 * làm được.
 */
export function SectionCard({ href, icon, title, description, pending }: SectionCardProps) {
  const inner = (
    <>
      <span className="section-card__icon" aria-hidden="true">
        <Icon name={icon} size={20} />
      </span>
      <span className="section-card__body">
        <span className="section-card__title">{title}</span>
        <span className="section-card__desc">{description}</span>
        {pending && (
          <span className="section-card__pending">
            <span className="tag tag--muted">{pending}</span>
          </span>
        )}
      </span>
      {/* Mũi tên chỉ ở thẻ bấm được. Trên thẻ chưa mở nó sẽ là một lời hứa sai. */}
      {href && !pending && (
        <span className="section-card__go" aria-hidden="true">
          <Icon name="arrow" size={18} />
        </span>
      )}
    </>
  );

  if (!href || pending) {
    return <div className="section-card section-card--off">{inner}</div>;
  }
  return (
    <Link to={href} className="card section-card">
      {inner}
    </Link>
  );
}

export function CardGrid({ children }: { children: React.ReactNode }) {
  return <div className="card-grid">{children}</div>;
}
