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

/** Ba nhóm giao diện (không phải năm vai trò): người vừa là LECTURER vừa là APPROVER cần một giao diện có cả hai mục. */
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
  /** Biểu tượng cạnh nhãn; bắt buộc vì một mục thiếu biểu tượng lệch hẳn 1.75rem so với các mục còn lại và trông như lỗi hiển thị. */
  icon: IconName;
  /** Người dùng phải có ít nhất một trong các vai trò này. Bỏ trống = mọi vai trò. */
  roles?: RoleCode[];
}

/**
 * Menu điều hướng.
 *
  * Chỉ là trải nghiệm người dùng: ẩn một mục không bảo vệ gì vì máy chủ kiểm vai trò ở mọi endpoint (`require_roles`).
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
      href: '/can-bo/lop',
      label: 'Lớp của tôi',
      icon: 'users',
      roles: ['LECTURER'],
    },
    {
      href: '/can-bo/ngan-hang-cau-hoi',
      label: 'Ngân hàng câu hỏi',
      icon: 'book',
      roles: ['ACADEMIC_MANAGER', 'LECTURER'],
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
    { href: '/quan-tri/ngan-hang-cau-hoi', label: 'Ngân hàng câu hỏi', icon: 'book' },
    { href: '/quan-tri/nhap-diem', label: 'Nhập điểm', icon: 'pencil' },
    { href: '/quan-tri/nhat-ky', label: 'Nhật ký thao tác', icon: 'log' },
    { href: '/quan-tri/dich-vu', label: 'Trạng thái dịch vụ', icon: 'pulse' },
    { href: '/thong-bao', label: 'Thông báo', icon: 'bell' },
  ],
};

export function visibleNav(workspace: Workspace, roles: RoleCode[]): NavItem[] {
  return NAV[workspace].filter((item) => !item.roles || item.roles.some((r) => roles.includes(r)));
}
