import { Link } from 'react-router-dom';
import type { TemplateRef } from '@/services/forms-api';
import { Icon } from '@/components/shared/Icon';

/**
 * Danh sách gọn — mỗi biểu mẫu một dòng mỏng, không phải ô vuông lớn. Trước
 * đây dùng lưới "bento" của trang chủ, nhưng chỗ dùng lại giờ chỉ còn trong
 * modal "Chọn biểu mẫu": bảy dòng ngắn đọc hết một màn hình, bảy ô lớn thì
 * phải cuộn qua gần hết modal mới chọn được.
 */
export function TemplateList({ active, pending }: { active: TemplateRef[]; pending: TemplateRef[] }) {
  return (
    <>
      <ul style={{ listStyle: 'none', margin: 0, padding: 0 }} className="picker-list">
        {active.map((t) => (
          <li key={t.id}>
            <Link to={`/sinh-vien/bieu-mau/${t.code}`} className="picker-row">
              <Icon name="form" size={18} className="picker-row__icon" />
              <span className="picker-row__body">
                <span className="picker-row__title">{t.name}</span>
                {t.description && <span className="picker-row__desc">{t.description}</span>}
              </span>
              <Icon name="arrow" size={16} className="picker-row__go" />
            </Link>
          </li>
        ))}
      </ul>

      {pending.length > 0 && (
        <section style={{ marginTop: 'var(--gap-5)' }}>
          <h2 className="eyebrow" style={{ marginBottom: 'var(--gap-3)' }}>
            Chưa mở trong phiên bản này
          </h2>
          <p style={{ fontSize: '0.8125rem', color: 'var(--ink-soft)', margin: '0 0 var(--gap-3)', maxWidth: 'var(--measure)' }}>
            Các biểu mẫu này đã có trong hệ thống nhưng chưa được làm trọn vẹn luồng lập đơn,
            ký và trình duyệt. Liệt kê ở đây để bạn biết chúng tồn tại, chứ không phải để bấm
            vào rồi gặp trang lỗi.
          </p>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }} className="picker-list">
            {pending.map((t) => (
              <li key={t.id}>
                <span className="picker-row picker-row--off">
                  <Icon name="form" size={18} className="picker-row__icon" />
                  <span className="picker-row__body">
                    <span className="picker-row__title">{t.name}</span>
                  </span>
                  <span className="tag tag--muted">chưa mở</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
