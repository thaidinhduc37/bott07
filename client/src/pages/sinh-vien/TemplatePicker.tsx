import { useTemplates } from '@/hooks/useTemplates';
import { TemplateList } from '@/components/forms/TemplateList';
import { PageHeader } from '@/components/shared/PageHeader';

/** Trang riêng để chọn biểu mẫu trước khi lập đơn mới — tách khỏi "Đơn của
 * tôi" thành route của chính nó thay vì hiện trong modal, dễ quản lý/đặt
 * link/nút quay lại trình duyệt hơn. */
export default function TemplatePickerPage() {
  const { active, pending, loading, error } = useTemplates();

  return (
    <div className="stack">
      <PageHeader
        breadcrumb={[{ label: 'Đơn của tôi', to: '/sinh-vien/bieu-mau' }, { label: 'Chọn biểu mẫu' }]}
        title="Chọn biểu mẫu"
        description="Hệ thống điền sẵn họ tên, mã học viên, lớp, khóa, hệ đào tạo và ngày sinh từ hồ sơ của bạn. Bạn chỉ nhập phần hồ sơ không có."
      />

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}
      {loading ? <p className="eyebrow">Đang tải…</p> : <TemplateList active={active} pending={pending} />}
    </div>
  );
}
