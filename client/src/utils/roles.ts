import type { IconName } from '@/components/shared/Icon';

export type RoleCode = 'ADMIN' | 'ACADEMIC_MANAGER' | 'LECTURER' | 'APPROVER' | 'STUDENT' | 'DEPARTMENT_HEAD';

export const ROLE_LABEL: Record<RoleCode, string> = {
  ADMIN: 'Quản trị viên',
  ACADEMIC_MANAGER: 'Cán bộ quản lý đào tạo',
  LECTURER: 'Giáo viên bộ môn',
  APPROVER: 'Cán bộ phê duyệt',
  STUDENT: 'Học viên',
  DEPARTMENT_HEAD: 'Lãnh đạo Khoa',
};

/**
 * Ba nhóm giao diện, không phải năm.
 *
 * Năm vai trò nhưng chỉ ba dashboard: một người vừa là LECTURER vừa là APPROVER
 * không cần hai giao diện, họ cần một giao diện có cả hai mục. Nhóm hóa ở đây để
 * menu và trang chủ không phải tự suy diễn ở mỗi chỗ dùng.
 */
export type Workspace = 'sinh-vien' | 'can-bo' | 'quan-tri';

export function workspaceOf(roles: RoleCode[]): Workspace {
  if (roles.includes('ADMIN')) return 'quan-tri';
  // Lãnh đạo Khoa cũng làm việc ở khu cán bộ (trước đây rơi vào khu học viên).
  if (roles.some((r) => r === 'ACADEMIC_MANAGER' || r === 'LECTURER' || r === 'APPROVER' || r === 'DEPARTMENT_HEAD')) {
    return 'can-bo';
  }
  return 'sinh-vien';
}

export function homePathOf(roles: RoleCode[]): string {
  return `/${workspaceOf(roles)}`;
}

export interface NavItem {
  href: string;
  label: string;
  /**
   * Biểu tượng cạnh nhãn.
   *
   * Bắt buộc, không phải tùy chọn: một mục thiếu biểu tượng trong danh sách dọc
   * sẽ lệch hẳn 1.75rem so với các mục còn lại, và chỗ trống đó trông giống lỗi
   * hiển thị. Bắt buộc ở kiểu dữ liệu thì trình biên dịch nhắc, không cần ai nhớ.
   */
  icon: IconName;
  /** Người dùng phải có ít nhất một trong các vai trò này. Bỏ trống = mọi vai trò. */
  roles?: RoleCode[];
  /**
   * Vì sao mục này chưa mở — một câu ngắn, hiển thị khi rê chuột.
   *
   * Có mặt nghĩa là trang chưa tồn tại: menu hiển thị nhãn mờ thay vì liên kết.
   * Nếu để nguyên `<Link>`, Next.js sẽ prefetch và ghi một loạt lỗi 404 vào
   * console, còn người dùng bấm vào thì gặp trang lỗi. Xóa thuộc tính này khi
   * trang tương ứng đã xong.
   *
   * Trước đây trường này là `availableFromDay: number` và menu hiện "Sẽ mở ở
   * Ngày 7". Mốc đó trôi qua mà trang vẫn chưa có, nên giao diện quay ra hứa
   * một ngày đã ở trong quá khứ. Một lời hứa tự hết hạn thì tệ hơn không hứa:
   * nêu điều kiện thật thì nó vẫn đúng ở bất kỳ thời điểm nào người dùng đọc.
   */
  blockedBy?: string;
}

/**
 * Menu điều hướng.
 *
 * Đây thuần túy là trải nghiệm người dùng. Việc một mục không hiện lên **không**
 * bảo vệ gì cả — mọi endpoint tương ứng đều có `@Roles()` ở NestJS. Nếu chỉ ẩn ở
 * đây thì bất kỳ ai gõ thẳng URL cũng vào được.
 */
export const NAV: Record<Workspace, NavItem[]> = {
  'sinh-vien': [
    { href: '/sinh-vien', label: 'Trang chủ', icon: 'home' },
    { href: '/sinh-vien/hoi-dap', label: 'Hỏi đáp', icon: 'chat' },
    { href: '/sinh-vien/on-tap', label: 'Ôn tập', icon: 'book' },
    { href: '/sinh-vien/lich', label: 'Lịch học & lịch thi', icon: 'calendar' },
    { href: '/sinh-vien/ket-qua', label: 'Kết quả học tập', icon: 'log' },
    { href: '/sinh-vien/bieu-mau', label: 'Biểu mẫu', icon: 'form' },
    { href: '/thong-bao', label: 'Thông báo', icon: 'bell' },
  ],
  'can-bo': [
    { href: '/can-bo', label: 'Trang chủ', icon: 'home' },
    {
      href: '/can-bo/don-cho-xu-ly',
      label: 'Đơn chờ xử lý',
      icon: 'inbox',
      roles: ['APPROVER', 'ACADEMIC_MANAGER'],
    },
    {
      href: '/can-bo/tai-lieu',
      label: 'Tài liệu',
      icon: 'folder',
      roles: ['ACADEMIC_MANAGER', 'LECTURER'],
    },
    {
      href: '/can-bo/lich',
      label: 'Lịch học & lịch thi',
      icon: 'calendar',
      roles: ['ACADEMIC_MANAGER', 'LECTURER'],
    },
    {
      href: '/can-bo/dao-tao',
      label: 'Quản lý đào tạo',
      icon: 'users',
      roles: ['ACADEMIC_MANAGER', 'DEPARTMENT_HEAD'],
    },
    {
      href: '/can-bo/nhap-diem',
      label: 'Nhập điểm',
      icon: 'pencil',
      roles: ['ACADEMIC_MANAGER', 'LECTURER'],
    },
    {
      href: '/can-bo/hoc-tap',
      label: 'Tình hình học tập',
      icon: 'pulse',
      roles: ['ACADEMIC_MANAGER', 'LECTURER'],
    },
    { href: '/can-bo/hoi-dap', label: 'Hỏi đáp quy chế', icon: 'chat' },
    { href: '/thong-bao', label: 'Thông báo', icon: 'bell' },
  ],
  'quan-tri': [
    { href: '/quan-tri', label: 'Trang chủ', icon: 'home' },
    { href: '/quan-tri/tai-khoan', label: 'Tài khoản', icon: 'users' },
    { href: '/quan-tri/tai-lieu', label: 'Tài liệu', icon: 'folder' },
    { href: '/quan-tri/dao-tao', label: 'Quản lý đào tạo', icon: 'book' },
    { href: '/quan-tri/lich', label: 'Lịch học & lịch thi', icon: 'calendar' },
    { href: '/quan-tri/nhap-diem', label: 'Nhập điểm', icon: 'pencil' },
    { href: '/quan-tri/nhat-ky', label: 'Nhật ký thao tác', icon: 'log' },
    { href: '/quan-tri/dich-vu', label: 'Trạng thái dịch vụ', icon: 'pulse' },
    { href: '/thong-bao', label: 'Thông báo', icon: 'bell' },
  ],
};

export function visibleNav(workspace: Workspace, roles: RoleCode[]): NavItem[] {
  return NAV[workspace].filter((item) => !item.roles || item.roles.some((r) => roles.includes(r)));
}
