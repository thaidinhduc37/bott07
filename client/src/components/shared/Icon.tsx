/**
 * Bộ biểu tượng Material Symbols Outlined (webfont nạp qua Google Fonts trong `index.html`, cùng domain với `Be Vietnam Pro`).
 * `aria-hidden` là mặc định vì icon luôn đi kèm nhãn chữ; đứng một mình thì bắt buộc truyền `title` (thành `role="img"` + `aria-label`).
 * Bảng ánh xạ giữ `IconName` nên nơi gọi `<Icon name="…">` không đổi.
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
  | 'pin'
  | 'help'
  | 'thumbUp'
  | 'thumbDown'
  | 'chevronLeft'
  | 'chevronRight';

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
  help: 'help',
  thumbUp: 'thumb_up',
  thumbDown: 'thumb_down',
  chevronLeft: 'chevron_left',
  chevronRight: 'chevron_right',
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
