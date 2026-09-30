/**
 * Bộ biểu tượng — Material Symbols Outlined (webfont, nạp qua Google Fonts
 * trong `index.html`).
 *
 * Trước đây mỗi biểu tượng là một nét vẽ SVG 24×24 nội tuyến, dựng riêng vì ba
 * lý do: mạng nội bộ Học viện có thể chặn CDN ngoài, webfont icon đặt hình vào
 * ký tự riêng tư gây khó cho trình đọc màn hình, và cả bộ font quá nặng cho
 * mười hai icon thực dùng.
 *
 * Đổi sang Material Symbols vì mockup thiết kế mới dùng đúng bộ này làm ngôn
 * ngữ hình ảnh chủ đạo (cùng họ với Google Fonts đã nạp cho chữ), và ba lý do
 * trên vẫn được giữ nguyên ở đây:
 *
 * 1. Icon giờ tải qua CÙNG domain Google Fonts mà `Plus Jakarta Sans` đã nạp —
 *    không thêm một CDN thứ hai.
 * 2. `aria-hidden` vẫn là mặc định: icon luôn đi kèm nhãn chữ trong ứng dụng
 *    này. Đứng một mình thì bắt buộc truyền `title`, lúc đó `role="img"` và
 *    tên biểu tượng không còn lọt vào cây trợ năng dưới dạng text vô nghĩa vì
 *    nó bị `aria-hidden` cùng span cha khi không có title, hoặc được thay bằng
 *    `aria-label` khi có.
 * 3. Bảng ánh xạ dưới đây giữ nguyên `IconName` — mọi nơi gọi `<Icon name="…">`
 *    trong 15 chỗ dùng của ứng dụng không phải sửa gì.
 */

export type IconName =
  | 'home'
  | 'chat'
  | 'book'
  | 'calendar'
  | 'form'
  | 'inbox'
  | 'bell'
  | 'users'
  | 'folder'
  | 'log'
  | 'pulse'
  | 'signature'
  | 'quote'
  | 'logout'
  | 'menu'
  | 'close'
  | 'send'
  | 'arrow'
  | 'check'
  | 'lock'
  | 'search'
  | 'pencil'
  | 'trash'
  | 'sun'
  | 'moon'
  | 'location'
  | 'person'
  | 'plus'
  | 'pin';

/** Tên biểu tượng tương ứng trong bộ Material Symbols Outlined. */
const SYMBOL: Record<IconName, string> = {
  home: 'home',
  chat: 'chat',
  book: 'menu_book',
  calendar: 'calendar_month',
  form: 'description',
  inbox: 'inbox',
  bell: 'notifications',
  users: 'group',
  folder: 'folder',
  log: 'receipt_long',
  pulse: 'monitoring',
  signature: 'draw',
  quote: 'format_quote',
  logout: 'logout',
  menu: 'menu',
  close: 'close',
  send: 'send',
  arrow: 'arrow_forward',
  check: 'check',
  lock: 'lock',
  search: 'search',
  pencil: 'edit',
  trash: 'delete',
  sun: 'light_mode',
  moon: 'dark_mode',
  location: 'location_on',
  person: 'person',
  plus: 'add',
  pin: 'push_pin',
};

export interface IconProps {
  name: IconName;
  /** Cỡ theo pixel CSS. Mặc định 18 — hợp với chữ 0.875rem. */
  size?: number;
  /** Đặt khi biểu tượng đứng một mình và mang nghĩa. */
  title?: string;
  className?: string;
  style?: React.CSSProperties;
}

export function Icon({ name, size = 18, title, className, style }: IconProps) {
  return (
    <span
      className={`material-symbols-outlined${className ? ` ${className}` : ''}`}
      style={{ fontSize: size, width: size, height: size, overflow: 'hidden', color: 'currentColor', ...style }}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {SYMBOL[name]}
    </span>
  );
}
