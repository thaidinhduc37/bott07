import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Icon } from '@/components/shared/Icon';
import { PageHeader } from '@/components/shared/PageHeader';
import { TabPanel, Tabs } from '@/components/shared/Tabs';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { ApiError } from '@/services/api';
import { supportApi, type SupportContact, type SupportGuide, type SupportProcedure } from '@/services/support-api';

type Tab = 'thu-tuc' | 'lien-he' | 'cau-hoi';

/** Bỏ dấu và chữ hoa để tìm "hoan thi" ra "Hoãn thi". */
const fold = (s: string) =>
  s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D')
    .toLowerCase();

function Procedure({ p }: { p: SupportProcedure }) {
  const required = p.fields.filter((f) => f.required);
  const optional = p.fields.filter((f) => !f.required);
  return (
    <details className="sup-item">
      <summary className="sup-item__head">
        <span className="sup-item__name">{p.name}</span>
        <span className="sup-item__meta">
          {p.approvalSteps.length > 0 ? `${p.approvalSteps.length} cấp duyệt` : 'Không cần trình ký'}
        </span>
      </summary>

      <div className="sup-item__body">
        {p.description && <p className="sup-item__desc">{p.description}</p>}

        <div className="sup-cols">
          <section>
            <h3 className="sup-h">Đơn đi qua những cấp nào</h3>
            {p.approvalSteps.length === 0 ? (
              <p className="sup-muted">Không có cấp duyệt nào.</p>
            ) : (
              <ol className="sup-steps">
                {p.approvalSteps.map((s) => (
                  <li key={s.order} className="sup-steps__item">
                    <span className="sup-steps__no" aria-hidden="true">
                      {s.order}
                    </span>
                    {s.title}
                  </li>
                ))}
              </ol>
            )}
            <p className="sup-muted">Bạn ký trước, rồi đơn lần lượt qua từng cấp; cấp sau chỉ nhận khi cấp trước đã quyết.</p>
          </section>

          <section>
            <h3 className="sup-h">Bạn cần điền</h3>
            {p.fields.length === 0 ? (
              <p className="sup-muted">Không có ô nào — toàn bộ lấy từ hồ sơ của bạn.</p>
            ) : (
              <ul className="sup-fields">
                {required.map((f) => (
                  <li key={f.label}>
                    {f.label} <span className="sup-req">bắt buộc</span>
                  </li>
                ))}
                {optional.map((f) => (
                  <li key={f.label}>{f.label}</li>
                ))}
              </ul>
            )}
            <p className="sup-muted">Họ tên, mã học viên, lớp, khóa, hệ đào tạo, ngày sinh được lấy sẵn từ hồ sơ.</p>
          </section>
        </div>

        <div className="sup-item__actions">
          <Link to={`/sinh-vien/bieu-mau/${p.code}`} className="btn btn--primary">
            Lập đơn này
          </Link>
        </div>
      </div>
    </details>
  );
}

function ContactCard({ c }: { c: SupportContact }) {
  const rows: { label: string; value: string; href?: string }[] = [];
  if (c.email) rows.push({ label: 'Email', value: c.email, href: `mailto:${c.email}` });
  if (c.phone) rows.push({ label: 'Điện thoại', value: c.phone, href: `tel:${c.phone.replace(/\s+/g, '')}` });
  if (c.location) rows.push({ label: 'Địa điểm', value: c.location });
  if (c.hours) rows.push({ label: 'Giờ làm việc', value: c.hours });
  return (
    <article className="sheet sheet--pad sup-contact">
      <h3 className="sup-contact__name">{c.name}</h3>
      {c.role && <p className="sup-contact__role">{c.role}</p>}
      {rows.length > 0 ? (
        <dl className="sup-contact__rows">
          {rows.map((r) => (
            <div key={r.label} className="sup-contact__row">
              <dt>{r.label}</dt>
              <dd>{r.href ? <a href={r.href}>{r.value}</a> : r.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="sup-muted">Chưa cập nhật thông tin liên hệ. Hãy đến trực tiếp phòng hoặc hỏi giáo viên chủ nhiệm.</p>
      )}
    </article>
  );
}

export default function Support() {
  useDocumentTitle('Hỗ trợ');
  const [params, setParams] = useSearchParams();
  const raw = params.get('tab');
  const tab: Tab = raw === 'lien-he' || raw === 'cau-hoi' ? raw : 'thu-tuc';
  const [guide, setGuide] = useState<SupportGuide | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    supportApi
      .guide()
      .then(setGuide)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Không tải được nội dung hỗ trợ'));
  }, []);

  function changeTab(next: Tab) {
    const p = new URLSearchParams(params);
    p.set('tab', next);
    setParams(p, { replace: true });
  }

  const procedures = useMemo(() => {
    const q = fold(query.trim());
    return (guide?.procedures ?? []).filter((p) => !q || fold(p.name).includes(q));
  }, [guide, query]);

  return (
    <div className="stack">
      <PageHeader
        title="Hỗ trợ"
        description="Hướng dẫn thủ tục, nơi liên hệ và câu hỏi thường gặp."
        actions={
          <Link to="/sinh-vien/hoi-dap" className="btn btn--ghost">
            <Icon name="chat" size={16} />
            Hỏi trợ lý
          </Link>
        }
        tabs={
          <Tabs
            label="Nội dung trang Hỗ trợ"
            idPrefix="ho-tro"
            value={tab}
            onChange={changeTab}
            items={[
              { id: 'thu-tuc', label: 'Thủ tục' },
              { id: 'lien-he', label: 'Liên hệ' },
              { id: 'cau-hoi', label: 'Câu hỏi thường gặp' },
            ]}
          />
        }
      />

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}
      {!guide && !error && <p className="eyebrow">Đang tải…</p>}

      {guide && (
        <TabPanel idPrefix="ho-tro" tab={tab}>
          {tab === 'thu-tuc' && (
            <div className="stack">
              <div className="field sup-search">
                <label className="field__label" htmlFor="sup-q">
                  Tìm thủ tục
                </label>
                <input
                  id="sup-q"
                  className="field__input"
                  type="search"
                  placeholder="Ví dụ: hoãn thi, học lại, nghỉ học"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>

              {procedures.length === 0 ? (
                <div className="empty">
                  <p className="empty__title">Không có thủ tục nào khớp</p>
                  <p>Thử từ khóa khác, hoặc hỏi trợ lý ở nút phía trên.</p>
                </div>
              ) : (
                <div className="sheet sup-list">
                  {procedures.map((p) => (
                    <Procedure key={p.code} p={p} />
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === 'lien-he' &&
            (guide.contacts.length === 0 ? (
              <div className="empty">
                <p className="empty__title">Chưa có thông tin liên hệ</p>
              </div>
            ) : (
              <div className="sup-contacts">
                {guide.contacts.map((c) => (
                  <ContactCard key={c.name} c={c} />
                ))}
              </div>
            ))}

          {tab === 'cau-hoi' &&
            (guide.faq.length === 0 ? (
              <div className="empty">
                <p className="empty__title">Chưa có câu hỏi thường gặp</p>
              </div>
            ) : (
              <div className="sheet sup-list">
                {guide.faq.map((f) => (
                  <details key={f.q} className="sup-item">
                    <summary className="sup-item__head">
                      <span className="sup-item__name">{f.q}</span>
                    </summary>
                    <div className="sup-item__body">
                      <p className="sup-item__desc">{f.a}</p>
                    </div>
                  </details>
                ))}
              </div>
            ))}
        </TabPanel>
      )}
    </div>
  );
}
