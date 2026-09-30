import { Link } from 'react-router-dom';
import { useMySubmissions } from '@/hooks/useMySubmissions';
import { SubmissionList } from '@/components/forms/SubmissionList';
import { Icon } from '@/components/shared/Icon';
import { PageHeader } from '@/components/shared/PageHeader';

/**
 * Trang chính là "Đơn của tôi" — đây là thứ học viên cần xem mỗi lần ghé qua
 * (đơn đang ở bước nào, có bị yêu cầu bổ sung không...). "Tạo đơn mới" và
 * "Chi tiết" đều là trang riêng (`/sinh-vien/bieu-mau/moi`, `/sinh-vien/
 * don-cua-toi/:id`) — không phải modal, để mỗi luồng có địa chỉ, nút quay
 * lại của trình duyệt và lịch sử điều hướng riêng, dễ quản lý hơn.
 */
export default function TemplateListPage() {
  const submissions = useMySubmissions();

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Hành chính"
        title="Đơn của tôi"
        actions={
          <Link to="/sinh-vien/bieu-mau/moi" className="btn btn--primary">
            <Icon name="plus" size={16} />
            Tạo đơn mới
          </Link>
        }
      />

      {submissions.error && (
        <div className="notice notice--error" role="alert">
          {submissions.error}
        </div>
      )}
      {submissions.loading ? (
        <p className="eyebrow">Đang tải…</p>
      ) : (
        <SubmissionList items={submissions.items} />
      )}
    </div>
  );
}
