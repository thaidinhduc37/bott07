import { Link, Outlet } from 'react-router-dom';
import { SessionProvider, useSession } from '@/components/shared/SessionProvider';
import { Icon } from '@/components/shared/Icon';
import { UserMenu } from '@/components/shared/UserMenu';
import { ROLE_LABEL, homePathOf } from '@/utils/roles';

function ProfileChrome() {
  const { user, loading, logout } = useSession();

  return (
    <div style={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column' }}>
      <header className="content-topbar" style={{ justifyContent: 'space-between' }}>
        <Link
          to={user ? homePathOf(user.roles) : '/'}
          style={{ textDecoration: 'none', color: 'var(--ink)', fontSize: '0.875rem' }}
        >
          ← Về trang chủ
        </Link>
        {!loading && user && (
          <div className="content-topbar__actions">
            <Link to="/thong-bao" className="btn btn--ghost btn--icon" aria-label="Thông báo">
              <Icon name="bell" size={18} />
            </Link>
            <UserMenu
              fullName={user.fullName}
              roleSummary={user.roles.map((r) => ROLE_LABEL[r]).join(', ')}
              onLogout={() => void logout()}
            />
          </div>
        )}
      </header>
      <main
        id="noi-dung"
        style={{
          flex: 1,
          maxWidth: '52rem',
          width: '100%',
          margin: '0 auto',
          padding: 'clamp(1.5rem, 4vw, 3rem) clamp(1rem, 3vw, 2rem)',
        }}
      >
        <Outlet />
      </main>
    </div>
  );
}

export default function ProfileLayout() {
  return (
    <SessionProvider>
      <ProfileChrome />
    </SessionProvider>
  );
}
