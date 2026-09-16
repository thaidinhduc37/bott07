import { SessionProvider } from '@/components/shared/SessionProvider';
import { Outlet } from 'react-router-dom';
import { AppShell } from '@/components/shared/AppShell';

export default function StudentLayout() {
  return (
    <SessionProvider>
      <AppShell workspace="sinh-vien">
        <Outlet />
      </AppShell>
    </SessionProvider>
  );
}
