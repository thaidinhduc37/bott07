import { Route, Routes } from 'react-router-dom';

import HomePage from '@/pages/Home';
import LoginPage from '@/pages/Login';
import NotificationsPage from '@/pages/Notifications';
import ProfilePage from '@/pages/Profile';
import ProfileLayout from '@/layout/ProfileLayout';

import StudentLayout from '@/layout/StudentLayout';
import StudentHome from '@/pages/sinh-vien/StudentHome';
import StudentChatPage from '@/pages/sinh-vien/StudentChat';
import StudentSchedulePage from '@/pages/sinh-vien/StudentSchedule';
import TemplateListPage from '@/pages/sinh-vien/Templates';
import TemplatePickerPage from '@/pages/sinh-vien/TemplatePicker';
import NewSubmissionPage from '@/pages/sinh-vien/NewSubmission';
import SubmissionDetailPage from '@/pages/sinh-vien/SubmissionDetail';

import StaffLayout from '@/layout/StaffLayout';
import StaffHome from '@/pages/can-bo/StaffHome';
import StaffChatPage from '@/pages/can-bo/StaffChat';
import StaffSchedulePage from '@/pages/can-bo/StaffSchedule';
import StaffDocumentsPage from '@/pages/can-bo/StaffDocuments';
import ApprovalInboxPage from '@/pages/can-bo/ApprovalInbox';
import ApprovalDetailPage from '@/pages/can-bo/ApprovalDetail';

import AdminLayout from '@/layout/AdminLayout';
import AdminHome from '@/pages/quan-tri/AdminHome';
import AccountsPage from '@/pages/quan-tri/Accounts';
import AuditLogPage from '@/pages/quan-tri/AuditLog';
import ServicesPage from '@/pages/quan-tri/Services';
import AdminDocumentsPage from '@/pages/quan-tri/AdminDocuments';

export function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/dang-nhap" element={<LoginPage />} />

      <Route element={<ProfileLayout />}>
        <Route path="/ho-so" element={<ProfilePage />} />
        <Route path="/thong-bao" element={<NotificationsPage />} />
      </Route>

      <Route path="/sinh-vien" element={<StudentLayout />}>
        <Route index element={<StudentHome />} />
        <Route path="hoi-dap" element={<StudentChatPage />} />
        <Route path="lich" element={<StudentSchedulePage />} />
        <Route path="bieu-mau" element={<TemplateListPage />} />
        <Route path="bieu-mau/moi" element={<TemplatePickerPage />} />
        <Route path="bieu-mau/:code" element={<NewSubmissionPage />} />
        <Route path="don-cua-toi/:id" element={<SubmissionDetailPage />} />
      </Route>

      <Route path="/can-bo" element={<StaffLayout />}>
        <Route index element={<StaffHome />} />
        <Route path="hoi-dap" element={<StaffChatPage />} />
        <Route path="lich" element={<StaffSchedulePage />} />
        <Route path="tai-lieu" element={<StaffDocumentsPage />} />
        <Route path="don-cho-xu-ly" element={<ApprovalInboxPage />} />
        <Route path="don-cho-xu-ly/:id" element={<ApprovalDetailPage />} />
      </Route>

      <Route path="/quan-tri" element={<AdminLayout />}>
        <Route index element={<AdminHome />} />
        <Route path="tai-khoan" element={<AccountsPage />} />
        <Route path="nhat-ky" element={<AuditLogPage />} />
        <Route path="dich-vu" element={<ServicesPage />} />
        <Route path="tai-lieu" element={<AdminDocumentsPage />} />
      </Route>
    </Routes>
  );
}
