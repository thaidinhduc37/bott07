import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useSession } from './SessionProvider';
import { Icon, type IconName } from './Icon';
import { UserMenu } from './UserMenu';
import { ROLE_LABEL, visibleNav, workspaceOf, type Workspace } from '@/utils/roles';

const WORKSPACE_LABEL: Record<Workspace, string> = {
  'sinh-vien': 'Khu vực học viên',
  'can-bo': 'Khu vực cán bộ',
  'quan-tri': 'Khu vực quản trị',
};

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: 'grid', placeItems: 'center', minHeight: '100dvh', padding: '1rem' }}>
      {children}
    </div>
  );
}

/** Ô định danh + tên sản phẩm. Dùng ở cả thanh bên lẫn thanh trên cùng. */
function Brand({ workspace }: { workspace: Workspace }) {
  return (
    <Link to={`/${workspace}`} className="rail__brand">
      <img className="rail__sigil" src="/logo.png" alt="" />
      <span style={{ minWidth: 0 }}>
        {/* Tên sản phẩm trước, tên đơn vị làm chú thích bên dưới. Đặt ngược lại
            thì tên đơn vị dài xuống hai dòng và đẩy tên sản phẩm — thứ người
            dùng thực sự bấm — xuống dưới ô định danh. */}
        <span className="rail__product">Trợ lý ảo</span>
        <span className="rail__org">Học viện KT &amp; CN An ninh</span>
      </span>
    </Link>
  );
}

export function AppShell({
  workspace,
  children,
}: {
  workspace: Workspace;
  children: React.ReactNode;
}) {
  const { user, loading, error, logout } = useSession();
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const railRef = useRef<HTMLElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);

  // Đổi trang thì đóng ngăn kéo. Trên màn hình hẹp nó phủ lên nội dung, nên để
  // nó mở sau khi điều hướng nghĩa là người dùng tới đúng trang mà không nhìn
  // thấy trang đó.
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  // Ngăn kéo đang mở thì Esc phải đóng được, và trang phía sau không được cuộn.
  //
  // Khóa cuộn quan trọng hơn vẻ ngoài: trên điện thoại, vuốt trên tấm phủ mà
  // trang bên dưới trôi đi là dấu hiệu kinh điển của một lớp phủ làm dối, và nó
  // khiến người dùng mất chỗ đang đọc khi đóng ngăn kéo lại.
  useEffect(() => {
    if (!menuOpen) return;

    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setMenuOpen(false);
    }
    document.addEventListener('keydown', onKey);

    // Đưa tiêu điểm vào ngăn kéo, nếu không người dùng bàn phím mở menu ra rồi
    // vẫn đứng ở nút bấm phía sau tấm phủ.
    railRef.current?.querySelector<HTMLElement>('a, button')?.focus();

    return () => {
      document.body.style.overflow = prev;
      document.removeEventListener('keydown', onKey);
    };
  }, [menuOpen]);

  function closeMenu() {
    setMenuOpen(false);
    // Trả tiêu điểm về đúng nút đã mở nó. Không làm thì tiêu điểm rơi về đầu
    // trang và người dùng bàn phím phải Tab lại từ đầu.
    toggleRef.current?.focus();
  }

  if (loading) {
    return (
      <Centered>
        <p className="eyebrow">Đang tải phiên làm việc…</p>
      </Centered>
    );
  }

  if (error) {
    return (
      <Centered>
        <div className="sheet sheet--pad" style={{ maxWidth: '32rem' }}>
          <div className="notice notice--error" role="alert">
            {error}
          </div>
        </div>
      </Centered>
    );
  }

  if (!user) return null;

  // Người dùng gõ thẳng URL của workspace không thuộc về mình. Backend đã chặn ở
  // tầng API; đây chỉ là lời giải thích thay cho một trang lỗi trống.
  const actual = workspaceOf(user.roles);
  if (actual !== workspace) {
    return (
      <Centered>
        <div className="sheet sheet--pad" style={{ maxWidth: '32rem' }}>
          <h1 className="display" style={{ fontSize: '1.35rem', margin: 0 }}>
            Khu vực này không dành cho vai trò của bạn
          </h1>
          <p style={{ color: 'var(--ink-soft)', marginTop: 'var(--gap-3)' }}>
            Tài khoản của bạn có vai trò {user.roleNames.join(', ')}.
          </p>
          <p style={{ marginTop: 'var(--gap-5)' }}>
            <Link to={`/${actual}`} className="btn btn--ghost">
              Về trang chủ của tôi
            </Link>
          </p>
        </div>
      </Centered>
    );
  }

  const nav = visibleNav(workspace, user.roles);
  // Sổ tay và Hỗ trợ của học viên không chiếm chỗ ở thanh bên: nằm trong menu hồ sơ.
  const accountLinks: { to: string; label: string; icon: IconName }[] =
    workspace === 'sinh-vien'
      ? [
          { to: '/sinh-vien/so-tay', label: 'Sổ tay', icon: 'pencil' },
          { to: '/sinh-vien/ho-tro', label: 'Hỗ trợ', icon: 'help' },
        ]
      : [];
  const accountActions = (
    <>
      <Link to="/thong-bao" className="btn btn--ghost btn--icon" aria-label="Thông báo">
        <Icon name="bell" size={18} />
      </Link>
      <UserMenu
        fullName={user.fullName}
        roleSummary={user.roles.map((r) => ROLE_LABEL[r]).join(', ')}
        links={accountLinks}
        onLogout={() => void logout()}
      />
    </>
  );

  return (
    <div className="shell">
      {/* Thanh trên cùng chỉ hiện dưới 60rem — xem `.topbar` trong styles/.
          Trên màn hình rộng, thanh bên đã mang cả thương hiệu lẫn điều hướng nên
          một thanh ngang nữa chỉ lấy mất chiều cao của nội dung. */}
      <header className="topbar">
        <button
          ref={toggleRef}
          type="button"
          className="btn btn--ghost btn--icon"
          aria-expanded={menuOpen}
          aria-controls="menu-chinh"
          aria-label={menuOpen ? 'Đóng menu' : 'Mở menu'}
          onClick={() => setMenuOpen((v) => !v)}
        >
          <Icon name={menuOpen ? 'close' : 'menu'} size={18} />
        </button>
        <Brand workspace={workspace} />
        <div className="topbar__actions">{accountActions}</div>
      </header>

      {/* Tấm phủ. Là `<button>` chứ không phải `<div onClick>`: nó có thể bấm
          được, nên nó phải tới được bằng bàn phím và phải nói được mình làm gì. */}
      <button
        type="button"
        className={`scrim${menuOpen ? ' scrim--on' : ''}`}
        tabIndex={menuOpen ? 0 : -1}
        aria-label="Đóng menu"
        onClick={closeMenu}
      />

      <nav
        ref={railRef}
        id="menu-chinh"
        className={`rail${menuOpen ? ' rail--open' : ''}`}
        aria-label="Điều hướng chính"
      >
        <div className="rail__head">
          <Brand workspace={workspace} />
        </div>

        <div className="rail__panel">
          <p className="rail__section">{WORKSPACE_LABEL[workspace]}</p>

          <ul className="rail__nav">
            {nav.map((item) => {
              const active =
                pathname === item.href ||
                (item.href !== `/${workspace}` && pathname.startsWith(`${item.href}/`));

              return (
                <li key={item.href}>
                  <Link
                    to={item.href}
                    className="rail__link"
                    aria-current={active ? 'page' : undefined}
                  >
                    <Icon name={item.icon} />
                    <span>{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      </nav>

      <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* Thanh ngang trên cùng CỦA TOÀN BỘ CỘT NỘI DUNG — không phải một dải
            nhỏ nằm lọt trong góc thanh bên. Đây là top app bar thật, kéo dài hết
            chiều rộng vùng nội dung (bên phải thanh bên), giống mockup: bên phải
            là cụm thông báo/giao diện/đăng xuất rồi tới danh tính người dùng. */}
        <header className="content-topbar">
          <div className="content-topbar__actions">{accountActions}</div>
        </header>

        {/* `key` buộc `<main>` dựng lại ở mỗi lần đổi trang, nên hoạt ảnh `rise`
            trong styles/ chạy lại. Không có nó thì layout của App Router giữ
            nguyên phần tử và hoạt ảnh chỉ chạy đúng một lần trong cả phiên. */}
        <main key={pathname} id="noi-dung" className="app-main">
          {children}
        </main>
      </div>
    </div>
  );
}
