import { Link } from 'react-router-dom';
import { useTemplates } from '@/hooks/useTemplates';
import { TemplateList } from '@/components/forms/TemplateList';
import { Icon } from '@/components/shared/Icon';

/** Trang riêng để chọn biểu mẫu trước khi lập đơn mới — tách khỏi "Đơn của
 * tôi" thành route của chính nó thay vì hiện trong modal, dễ quản lý/đặt
 * link/nút quay lại trình duyệt hơn. */
export default function TemplatePickerPage() {
  const { active, pending, loading, error } = useTemplates();

  return (
    <div className="stack shell--full">
      <header>
        <p style={{ margin: '0 0 var(--gap-2)' }}>
          <Link to="/sinh-vien/bieu-mau" className="btn btn--quiet">
            <Icon name="arrow" size={14} style={{ transform: 'rotate(180deg)' }} />
            Đơn của tôi
          </Link>
        </p>
        <span className="eyebrow">Lập đơn</span>
        <h1 className="display page-title">Chọn biểu mẫu</h1>
        <p className="page-sub">
          Hệ thống điền sẵn họ tên, mã học viên, lớp, khóa, hệ đào tạo và ngày sinh từ hồ sơ của
          bạn. Bạn chỉ nhập phần hồ sơ không có.
        </p>
      </header>

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}
      {loading ? <p className="eyebrow">Đang tải…</p> : <TemplateList active={active} pending={pending} />}
    </div>
  );
}
