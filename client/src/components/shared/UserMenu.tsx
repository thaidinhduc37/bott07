import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Icon, type IconName } from './Icon';
import { useTheme } from '@/hooks/useTheme';

/**
 * Hai chữ cái đầu của tên, lấy theo cách người Việt gọi nhau — xem
 * `AppShell.initialsOf` cho lý do đầy đủ. Trùng lặp có chủ đích: hai nơi dùng
 * độc lập, tách thành tiện ích dùng chung không đáng cho hai dòng logic.
 */
function initialsOf(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[parts.length - 2][0] + parts[parts.length - 1][0]).toUpperCase();
}

/**
 * Avatar ở góc thanh trên cùng, bấm vào xổ ra menu: giao diện sáng/tối, đổi
 * mật khẩu, thông tin hồ sơ, đăng xuất.
 *
 * Trước đây giao diện tối và đăng xuất là hai nút icon riêng nằm trần trong
 * thanh ngang — gộp vào đây để thanh ngang chỉ còn chuông thông báo + avatar,
 * đúng mật độ của mockup tham chiếu.
 */
export function UserMenu({
  fullName,
  roleSummary,
  links = [],
  onLogout,
}: {
  fullName: string;
  roleSummary: string;
  /** Liên kết phụ xếp ngay dưới "Thông tin hồ sơ" (vd Sổ tay, Hỗ trợ của học viên). */
  links?: { to: string; label: string; icon: IconName }[];
  onLogout: () => void;
}) {
  const { isDark, toggle: toggleTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;

    function onPointerDown(e: PointerEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="user-menu" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className="user-menu__trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Menu tài khoản — ${fullName}`}
        title={`${fullName} — ${roleSummary}`}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="rail__initials" aria-hidden="true">
          {initialsOf(fullName)}
        </span>
      </button>

      {open && (
        <div className="user-menu__panel" role="menu">
          <div className="user-menu__who">
            <strong>{fullName}</strong>
            <span>{roleSummary}</span>
          </div>
          <div className="user-menu__divider" />
          <button type="button" role="menuitem" className="user-menu__item" onClick={toggleTheme}>
            <Icon name={isDark ? 'sun' : 'moon'} size={18} />
            {isDark ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'}
          </button>
          <Link to="/ho-so?mode=password" role="menuitem" className="user-menu__item" onClick={() => setOpen(false)}>
            <Icon name="lock" size={18} />
            Đổi mật khẩu
          </Link>
          <Link to="/ho-so" role="menuitem" className="user-menu__item" onClick={() => setOpen(false)}>
            <Icon name="person" size={18} />
            Thông tin hồ sơ
          </Link>
          {links.map((l) => (
            <Link key={l.to} to={l.to} role="menuitem" className="user-menu__item" onClick={() => setOpen(false)}>
              <Icon name={l.icon} size={18} />
              {l.label}
            </Link>
          ))}
          <div className="user-menu__divider" />
          <button type="button" role="menuitem" className="user-menu__item user-menu__item--danger" onClick={onLogout}>
            <Icon name="logout" size={18} />
            Đăng xuất
          </button>
        </div>
      )}
    </div>
  );
}
