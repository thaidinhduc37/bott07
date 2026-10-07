import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Icon } from '@/components/shared/Icon';
import { formsApi, type TemplateRef } from '@/services/forms-api';

/**
 * Cột phụ của trang "Đơn của tôi": các mẫu đơn đang mở, bấm là vào form lập đơn ngay.
 * Chỉ liệt kê mẫu có thật trong hệ thống (`formsApi.templates`).
 */
export function TemplateCatalog() {
  const [items, setItems] = useState<TemplateRef[] | null>(null);

  useEffect(() => {
    void formsApi
      .templates()
      .then((r) => setItems(r.items.filter((t) => t.isActive)))
      .catch(() => setItems([]));
  }, []);

  return (
    <section className="sheet sheet--pad tpl-cat">
      <div className="tpl-cat__head">
        <h2 className="aside-h">Lập đơn mới</h2>
        {items && items.length > 0 && <span className="section-head__note">{items.length} mẫu</span>}
      </div>

      {items === null ? (
        <p className="eyebrow">Đang tải…</p>
      ) : items.length === 0 ? (
        <p className="home-aside__empty">Chưa có mẫu đơn nào đang mở.</p>
      ) : (
        <ul className="tpl-cat__list">
          {items.map((t) => (
            <li key={t.id}>
              <Link to={`/sinh-vien/bieu-mau/${t.code}`} className="tpl-cat__item">
                <span className="tpl-cat__icon" aria-hidden="true">
                  <Icon name="form" size={18} />
                </span>
                <span className="tpl-cat__body">
                  <span className="tpl-cat__name">{t.name}</span>
                  {t.description && <span className="tpl-cat__desc">{t.description}</span>}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <p className="tpl-cat__note">
        Chữ ký trong hệ thống là chữ ký điện tử nội bộ (mã băm và nhật ký), không phải chứng thư số công cộng.
      </p>
    </section>
  );
}
