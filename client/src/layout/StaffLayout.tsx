import { SessionProvider } from '@/components/shared/SessionProvider';
import { Outlet } from 'react-router-dom';
import { AppShell } from '@/components/shared/AppShell';

export default function StaffLayout() {
  return (
    <SessionProvider>
      <AppShell workspace="can-bo">
        <Outlet />
      </AppShell>
    </SessionProvider>
  );
}
