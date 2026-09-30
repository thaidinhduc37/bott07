import { Outlet } from 'react-router-dom';
import { AppShell } from '@/components/shared/AppShell';
import { SessionProvider, useSession } from '@/components/shared/SessionProvider';
import { workspaceOf } from '@/utils/roles';

/**
 * Thông báo và Hồ sơ dùng chung cho mọi vai trò nên không thuộc một khu vực cố định,
 * nhưng vẫn phải nằm trong đúng khung của khu vực người dùng đang ở — có thanh menu,
 * cùng bề rộng nội dung với mọi trang khác. Trước đây chúng có khung riêng (không menu,
 * rộng 52rem) nên lệch cả về bố cục lẫn chiều ngang.
 */
function ProfileChrome() {
  const { user } = useSession();
  // Chưa có `user` (đang tải) thì AppShell hiện màn hình chờ, giá trị này chưa được dùng.
  return (
    <AppShell workspace={user ? workspaceOf(user.roles) : 'sinh-vien'}>
      <Outlet />
    </AppShell>
  );
}

export default function ProfileLayout() {
  return (
    <SessionProvider>
      <ProfileChrome />
    </SessionProvider>
  );
}
