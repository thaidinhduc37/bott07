import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ApiError } from '@/services/api';
import {
  approvalsApi,
  type ApprovalActionType,
  type ApprovalDetail,
} from '@/services/approvals-api';
import { viDate, viDateTime } from '@/services/forms-api';
import { Field } from '@/components/shared/Field';
import { ApprovalFlow } from '@/components/forms/ApprovalFlow';
import { PageHeader } from '@/components/shared/PageHeader';

/** Hành động khả dụng theo trạng thái hiện tại của đơn. */
function actionsFor(status: string): ApprovalActionType[] {
  switch (status) {
    case 'SUBMITTED':
      return ['RECEIVE', 'REQUEST_REVISION', 'REJECT'];
    case 'UNDER_REVIEW':
      return ['APPROVE', 'REQUEST_REVISION', 'REJECT'];
    case 'APPROVED':
      return ['COMPLETE'];
    default:
      return [];
  }
}

const ACTION_STYLE: Partial<Record<ApprovalActionType, string>> = {
  APPROVE: 'btn--primary',
  COMPLETE: 'btn--primary',
  REJECT: 'btn--danger',
};

export default function ApprovalDetailPage() {
  const { id = '' } = useParams<{ id: string }>();

  const [d, setD] = useState<ApprovalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const [pending, setPending] = useState<ApprovalActionType | null>(null);
  const [comment, setComment] = useState('');
  const [pin, setPin] = useState('');

  const load = useCallback(async () => {
    try {
      setD(await approvalsApi.detail(id));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run() {
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await approvalsApi.act(id, pending, {
        comment: comment.trim() || undefined,
        pin: pin || undefined,
      });
      setD(updated);
      setFlash(`Đã ${LABEL[pending].toLowerCase()} ${updated.code}.`);
      setPending(null);
      setComment('');
      setPin('');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="eyebrow">Đang tải…</p>;
  if (!d) {
    return (
      <div className="stack">
        <div className="notice notice--error" role="alert">
          {error ?? 'Không tìm thấy đơn'}
        </div>
        <p>
          <Link to="/can-bo/don-cho-xu-ly" className="btn btn--ghost">
            ← Về hộp thư
          </Link>
        </p>
      </div>
    );
  }

  const myStep = d.steps.find((s) => s.canAct) ?? null;
  const available = myStep ? actionsFor(d.status) : [];

  return (
    <div className="stack">
      <PageHeader
        breadcrumb={[
          { label: 'Đơn chờ xử lý', to: '/can-bo/don-cho-xu-ly' },
          { label: d.code },
        ]}
        title={d.template.name}
        description={
          <>
            {d.owner.fullName}
            {d.owner.studentCode && <span className="mono"> · {d.owner.studentCode}</span>}
            {d.owner.className && ` · lớp ${d.owner.className}`}
          </>
        }
        actions={<span className="tag tag--pen">{d.statusLabel}</span>}
      />

      <div className="page-grid">
        <div className="page-grid__main">
          {flash && (
            <div className="notice notice--ok" role="status">
              {flash}
            </div>
          )}
          {error && (
            <div className="notice notice--error" role="alert">
              {error}
            </div>
          )}

          {/* --------------------------------------------------------- nội dung */}
          <section className="sheet sheet--pad">
            <div className="spread" style={{ marginBottom: 'var(--gap-4)' }}>
              <h2 className="eyebrow" style={{ margin: 0 }}>
                Nội dung đơn
              </h2>
              {d.hasFile && (
                <a className="btn btn--ghost" href={approvalsApi.fileUrl(d.id)}>
                  Tải file đơn
                </a>
              )}
            </div>
            <dl style={{ margin: 0, display: 'grid', gap: 'var(--gap-3)' }}>
              {d.fields.map((f) => {
                const value = f.autofill ? d.profileSnapshot[f.key] : d.formData[f.key];
                return (
                  <div
                    key={f.key}
                    style={{ display: 'grid', gridTemplateColumns: 'minmax(9rem, 14rem) 1fr', gap: 'var(--gap-4)', borderBottom: '1px dotted var(--rule)', paddingBottom: '0.4rem' }}
                  >
                    <dt style={{ fontSize: '0.8125rem', color: 'var(--ink-soft)' }}>{f.label}</dt>
                    <dd style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                      {f.type === 'date' && value ? viDate(`${value}T00:00:00+07:00`) : value || '—'}
                    </dd>
                  </div>
                );
              })}
            </dl>
            {d.signedHash && (
              <p style={{ margin: 'var(--gap-4) 0 0', fontSize: '0.75rem', color: 'var(--ink-faint)' }}>
                Mã băm bản đã ký:{' '}
                <span className="mono" style={{ wordBreak: 'break-all' }}>{d.signedHash}</span>
              </p>
            )}
          </section>

          {/* ---------------------------------------------------------- lịch sử */}
          <section className="sheet sheet--pad">
            <h2 className="eyebrow" style={{ marginBottom: 'var(--gap-4)' }}>
              Lịch sử xử lý
            </h2>
            <ol style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {d.history.map((h, i) => (
                <li
                  key={i}
                  style={{ borderTop: i ? '1px dotted var(--rule)' : 'none', padding: '0.55rem 0' }}
                >
                  <div className="spread" style={{ alignItems: 'baseline', gap: 'var(--gap-4)' }}>
                    <span style={{ fontSize: '0.875rem' }}>
                      <strong style={{ fontWeight: 500 }}>{h.actionLabel}</strong> — {h.actor}
                      {h.stepOrder !== null && (
                        <span style={{ color: 'var(--ink-faint)' }}> (bước {h.stepOrder})</span>
                      )}
                    </span>
                    <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', flexShrink: 0 }}>
                      {viDateTime(h.createdAt)}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--ink-faint)' }}>
                    {h.fromStatus ? `${h.fromStatus} → ${h.toStatus}` : h.toStatus}
                    {h.ipAddress && ` · ${h.ipAddress}`}
                  </div>
                  {h.comment && (
                    <p style={{ margin: '0.25rem 0 0', fontSize: '0.8125rem', color: 'var(--ink-soft)' }}>
                      “{h.comment}”
                    </p>
                  )}
                </li>
              ))}
            </ol>
          </section>
        </div>

        <aside className="page-grid__aside">
          {/* ------------------------------------------------------ các cấp duyệt */}
          <section className="sheet sheet--pad">
            <h2 className="aside-h">Các cấp duyệt</h2>
            <ApprovalFlow
              variant="vertical"
              steps={d.steps.map((st) => ({
                order: st.stepOrder,
                title: st.title,
                roleCode: st.roleCode,
                status: st.status,
                decidedAt: st.decidedAt,
                comment: st.comment,
              }))}
              currentStepOrder={d.currentStepOrder}
              submissionStatus={d.status}
            />
          </section>

          {/* ---------------------------------------------------------- quyết định */}
          {myStep ? (
            <section className="sheet sheet--pad">
              <h2 className="aside-h">
                Quyết định của bạn — bước {myStep.stepOrder}: {myStep.title}
              </h2>

              {!pending ? (
                <div className="appr-actions">
                  {available.map((a) => (
                    <button
                      key={a}
                      type="button"
                      className={`btn btn--block ${ACTION_STYLE[a] ?? 'btn--ghost'}`}
                      onClick={() => setPending(a)}
                    >
                      {LABEL[a]}
                    </button>
                  ))}
                </div>
              ) : (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void run();
                  }}
                >
                  <p style={{ margin: '0 0 var(--gap-4)', fontSize: '0.875rem' }}>
                    <strong style={{ fontWeight: 500 }}>{LABEL[pending]}</strong>
                    {pending === 'APPROVE' &&
                      ' — chữ ký của bạn sẽ được chèn vào ô của cấp này và đơn chuyển sang bước tiếp theo.'}
                    {pending === 'REQUEST_REVISION' &&
                      ' — đơn được mở khóa cho học viên sửa, và chữ ký cũ bị gỡ vì nó chứng nhận nội dung sắp thay đổi.'}
                    {pending === 'REJECT' && ' — đơn dừng hẳn tại đây.'}
                  </p>

                  {(pending === 'REJECT' || pending === 'REQUEST_REVISION') && (
                    <Field
                      as="textarea"
                      rows={3}
                      required
                      label={pending === 'REJECT' ? 'Lý do từ chối' : 'Cần bổ sung những gì'}
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      maxLength={1000}
                      hint="Học viên đọc được nguyên văn phần này."
                    />
                  )}
                  {pending === 'APPROVE' && (
                    <>
                      <Field
                        label="Ghi chú (không bắt buộc)"
                        value={comment}
                        onChange={(e) => setComment(e.target.value)}
                        maxLength={1000}
                      />
                      <Field
                        label="Mã PIN ký"
                        type="password"
                        inputMode="numeric"
                        autoComplete="off"
                        required
                        value={pin}
                        onChange={(e) => setPin(e.target.value)}
                        hint="Phê duyệt đồng nghĩa với ký vào đơn, nên phải xác nhận lại bằng mã PIN."
                      />
                    </>
                  )}

                  <div className="appr-actions">
                    <button
                      type="submit"
                      className={`btn btn--block ${ACTION_STYLE[pending] ?? 'btn--primary'}`}
                      disabled={busy}
                    >
                      {busy ? 'Đang xử lý…' : `Xác nhận ${LABEL[pending].toLowerCase()}`}
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost btn--block"
                      disabled={busy}
                      onClick={() => {
                        setPending(null);
                        setComment('');
                        setPin('');
                      }}
                    >
                      Hủy
                    </button>
                  </div>
                </form>
              )}
            </section>
          ) : (
            <div className="notice notice--info">
              {d.currentStepOrder === null
                ? 'Đơn đã đóng, không còn bước nào chờ xử lý.'
                : `Đơn đang ở bước ${d.currentStepOrder}, không thuộc phần việc của bạn.`}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

const LABEL: Record<ApprovalActionType, string> = {
  SUBMIT: 'Gửi trình ký',
  RESUBMIT: 'Gửi lại',
  RECEIVE: 'Tiếp nhận',
  APPROVE: 'Phê duyệt và ký',
  REJECT: 'Từ chối',
  REQUEST_REVISION: 'Yêu cầu bổ sung',
  SIGN: 'Ký',
  COMPLETE: 'Đánh dấu hoàn thành',
};
