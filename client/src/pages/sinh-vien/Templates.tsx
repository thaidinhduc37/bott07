import { Link } from 'react-router-dom';
import { useMySubmissions } from '@/hooks/useMySubmissions';
import { SubmissionList } from '@/components/forms/SubmissionList';
import { Icon } from '@/components/shared/Icon';

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
    <div className="stack shell--full">
      <header className="spread" style={{ alignItems: 'flex-end', gap: 'var(--gap-4)' }}>
        <div>
          <span className="eyebrow">Hành chính</span>
          <h1 className="display page-title">Đơn của tôi</h1>
        </div>
        <Link to="/sinh-vien/bieu-mau/moi" className="btn btn--primary" style={{ flexShrink: 0 }}>
          <Icon name="plus" size={16} />
          Tạo đơn mới
        </Link>
      </header>

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
