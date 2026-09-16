import { SessionProvider } from '@/components/shared/SessionProvider';
import { Outlet } from 'react-router-dom';
import { AppShell } from '@/components/shared/AppShell';

export default function AdminLayout() {
  return (
    <SessionProvider>
      <AppShell workspace="quan-tri">
        <Outlet />
      </AppShell>
    </SessionProvider>
  );
}
