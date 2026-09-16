import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@/components/shared/Icon';

/**
 * Khung soạn thảo toàn màn hình — phủ kín khung nhìn (`position: fixed;
 * inset: 0`), không cần đụng vào layout/route: sidebar và thanh trên cùng
 * của khu vực học viên vẫn còn render bên dưới, chỉ là bị che hoàn toàn.
 * Đúng tinh thần "lập đơn/xem đơn là một khung soạn thảo riêng, không phải
 * một trang con của ứng dụng" — giống các phần mềm quản lý văn bản điều
 * hành: một thanh tiêu đề mỏng, nút đóng ở góc, không có gì khác chia trí.
 */
export function ComposerChrome({
  title,
  subtitle,
  statusTag,
  closeTo,
  children,
}: {
  title: string;
  subtitle?: string;
  statusTag?: React.ReactNode;
  closeTo: string;
  children: React.ReactNode;
}) {
  const navigate = useNavigate();

  // Portal thẳng ra `document.body`, KHÔNG render tại chỗ trong cây
  // `AppShell`: `.app-main` (cha) có hoạt ảnh vào trang bằng `transform`
  // (xem `@keyframes rise`), và theo chuẩn CSS, một cha có `transform` (kể
  // cả đang giữa hoạt ảnh) trở thành "containing block" cho con
  // `position: fixed` bên trong nó — `inset: 0` khi đó chỉ phủ kín KHUNG
  // CỦA CHA chứ không phải khung nhìn thật, kết quả là composer co lại
  // đúng bằng kích thước phần tử cha thay vì toàn màn hình. Thoát ra ngoài
  // bằng portal thì `position: fixed` luôn tính theo khung nhìn thật.
  return createPortal(
    <div className="composer">
      <header className="composer__bar">
        <div className="composer__bar-text">
          <strong>{title}</strong>
          {subtitle && <span className="composer__bar-sub">{subtitle}</span>}
        </div>
        <div className="row" style={{ gap: 'var(--gap-4)', flexShrink: 0 }}>
          {statusTag}
          <button
            type="button"
            className="composer__close"
            aria-label="Đóng"
            onClick={() => navigate(closeTo)}
          >
            <Icon name="close" size={20} />
          </button>
        </div>
      </header>
      <div className="composer__body">
        <div className="composer__inner">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
