import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useNewSubmission } from '@/hooks/useNewSubmission';
import { SubmissionForm } from '@/components/forms/SubmissionForm';
import { ApprovalFlow } from '@/components/forms/ApprovalFlow';
import { ComposerChrome } from '@/components/forms/ComposerChrome';

type Tab = 'noi-dung' | 'noi-nhan' | 'dinh-kem';

const CANCEL_HREF = '/sinh-vien/bieu-mau';

/**
 * Lập đơn mới — cùng khung soạn thảo toàn màn hình (`ComposerChrome`) với
 * trang chi tiết đơn, xem docstring của component đó. `useNewSubmission`
 * sống ở đây (không phải trong một panel con) vì bar tiêu đề cần biết tên
 * biểu mẫu ngay khi đang tải.
 */
export default function NewSubmissionPage() {
  const { code = '' } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('noi-dung');
  const { tpl, loading, busy, error, fieldErrors, submit } = useNewSubmission(code, (id) =>
    navigate(`/sinh-vien/don-cua-toi/${id}`),
  );

  if (loading) {
    return (
      <ComposerChrome title="Đang tải…" closeTo={CANCEL_HREF}>
        <p className="eyebrow">Đang tải…</p>
      </ComposerChrome>
    );
  }

  if (error || !tpl) {
    return (
      <ComposerChrome title="Không tìm thấy biểu mẫu" closeTo={CANCEL_HREF}>
        <div className="notice notice--error" role="alert">
          {error ?? 'Không tìm thấy biểu mẫu'}
        </div>
      </ComposerChrome>
    );
  }

  const tabs: Array<{ value: Tab; label: string }> = [
    { value: 'noi-dung', label: 'Thông tin chi tiết' },
    { value: 'noi-nhan', label: 'Nơi nhận gửi' },
    { value: 'dinh-kem', label: 'Đính kèm văn bản' },
  ];

  return (
    <ComposerChrome title={tpl.name} subtitle="Lập đơn mới" closeTo={CANCEL_HREF}>
      <div className="doc-layout">
        <div className="stack">
          {tpl.missingProfileFields.length > 0 && (
            <div className="notice notice--warn" role="alert">
              Hồ sơ của bạn còn thiếu:{' '}
              <strong>{tpl.missingProfileFields.map((f) => f.label).join(', ')}</strong>. Những
              thông tin này do Phòng Quản lý học viên nhập, bạn không tự bổ sung được. Liên hệ
              Phòng để cập nhật trước khi lập đơn.
            </div>
          )}

          <div className="seg" style={{ width: '100%' }}>
            {tabs.map((t) => (
              <label
                key={t.value}
                className={`seg__opt${tab === t.value ? ' seg__opt--on' : ''}`}
                style={{ flex: 1, justifyContent: 'center', padding: '0.4rem 0.3rem', fontSize: '0.75rem', whiteSpace: 'normal', textAlign: 'center', lineHeight: 1.25 }}
              >
                <input type="radio" name="lap-don-tab" checked={tab === t.value} onChange={() => setTab(t.value)} />
                {t.label}
              </label>
            ))}
          </div>

          {tab === 'noi-dung' && (
            <section className="sheet sheet--pad">
              <SubmissionForm
                fields={tpl.fields}
                templateCode={code}
                autofill={tpl.autofill}
                busy={busy || tpl.missingProfileFields.length > 0}
                submitLabel="Lập đơn"
                fieldErrors={fieldErrors}
                onSubmit={submit}
                onCancel={() => navigate(CANCEL_HREF)}
              />
            </section>
          )}

          {tab === 'noi-nhan' && (
            <section className="sheet sheet--pad">
              {tpl.approvalFlow.length > 0 ? (
                <>
                  <ApprovalFlow
                    variant="vertical"
                    steps={tpl.approvalFlow.map((step) => ({ order: step.order, title: step.title, roleCode: step.roleCode }))}
                    currentStepOrder={null}
                  />
                  <p style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', margin: 'var(--gap-4) 0 0' }}>
                    Sau khi bạn ký và gửi, đơn lần lượt qua từng cấp trên — đơn chỉ chuyển tiếp khi
                    cấp trước đã quyết.
                  </p>
                </>
              ) : (
                <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--ink-soft)' }}>
                  Biểu mẫu này không cần trình ký cấp trên.
                </p>
              )}
            </section>
          )}

          {tab === 'dinh-kem' && (
            <section className="sheet sheet--pad">
              <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--ink-soft)' }}>
                Lập đơn xong mới đính kèm được — quay lại sau khi tạo đơn.
              </p>
            </section>
          )}
        </div>

        <aside className="doc-layout__aside stack">
          <section className="sheet sheet--pad">
            <h2 className="eyebrow" style={{ marginBottom: 'var(--gap-4)' }}>
              Bản in
            </h2>
            <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--ink-soft)' }}>
              Chưa có gì để xem trước — lập đơn xong rồi dựng bản in mới thấy đơn sẽ in ra như thế
              nào.
            </p>
          </section>
        </aside>
      </div>
    </ComposerChrome>
  );
}
