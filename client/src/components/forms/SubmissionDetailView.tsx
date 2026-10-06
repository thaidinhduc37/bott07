import { useState } from 'react';
import { formsApi, viDate, viDateTime, type SubmissionDetail, type VerifyResult } from '@/services/forms-api';
import { ApprovalFlow } from '@/components/forms/ApprovalFlow';
import { SignPanel } from '@/components/forms/SignPanel';
import { DocumentPreview } from '@/components/forms/DocumentPreview';

type Tab = 'noi-dung' | 'noi-nhan' | 'dinh-kem';

export function SubmissionDetailView({
  s,
  busy,
  editableFields,
  hasSignature,
  signError,
  verification,
  onSign,
  onEdit,
  onRender,
  onRunVerify,
  onSubmitForApproval,
  onDelete,
}: {
  s: SubmissionDetail;
  busy: boolean;
  editableFields: SubmissionDetail['template']['fields'];
  hasSignature: boolean;
  signError: string | null;
  verification: VerifyResult | null;
  onSign: (pin: string) => void;
  onEdit: () => void;
  onRender: () => void;
  onRunVerify: () => void;
  onSubmitForApproval: () => void;
  onDelete: () => void;
}) {
  const [tab, setTab] = useState<Tab>('noi-dung');
  const [signOpen, setSignOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  // Khớp đúng điều kiện backend chặn xóa (`FormsService.remove`): chỉ đơn
  // nháp CHƯA KÝ mới xóa được — ký rồi thì phải giữ lại cho vết kiểm chứng.
  const deletable = s.status === 'DRAFT' && !s.signedHash;
  const previewUrl = s.signedHash
    ? formsApi.fileUrl(s.id, 'signed')
    : s.generatedHash
      ? formsApi.fileUrl(s.id, 'unsigned')
      : null;

  const tabs: Array<{ value: Tab; label: string }> = [
    { value: 'noi-dung', label: 'Thông tin chi tiết' },
    { value: 'noi-nhan', label: 'Nơi nhận gửi' },
    { value: 'dinh-kem', label: 'Đính kèm văn bản' },
  ];

  return (
    <div className="doc-layout">
      {/* ------------------------------------------------------ cột nội dung */}
      <div className="stack">
        <div className="seg" style={{ width: '100%' }}>
          {tabs.map((t) => (
            <label
              key={t.value}
              className={`seg__opt${tab === t.value ? ' seg__opt--on' : ''}`}
              style={{ flex: 1, justifyContent: 'center', padding: '0.4rem 0.3rem', fontSize: '0.75rem', whiteSpace: 'normal', textAlign: 'center', lineHeight: 1.25 }}
            >
              <input type="radio" name="chi-tiet-tab" checked={tab === t.value} onChange={() => setTab(t.value)} />
              {t.label}
            </label>
          ))}
        </div>

        {tab === 'noi-dung' && (
          <section className="sheet sheet--pad">
            <dl style={{ margin: 0, display: 'grid', gap: 'var(--gap-3)' }}>
              {s.template.fields.map((f) => {
                const value = f.autofill ? s.profileSnapshot[f.key] : s.formData[f.key];
                // Trường dạng bảng xếp dọc (nhãn trên, bảng dưới chiếm cả bề ngang): nhét bảng nhiều cột
                // vào cột giá trị hẹp bên phải thì bề rộng tối thiểu của bảng đẩy nó ra ngoài khung.
                const isTable = Array.isArray(value) && value.length > 0;
                return (
                  <div
                    key={f.key}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: isTable ? 'minmax(0, 1fr)' : 'minmax(9rem, 14rem) minmax(0, 1fr)',
                      gap: isTable ? 'var(--gap-2)' : 'var(--gap-4)',
                      borderBottom: '1px dotted var(--rule)',
                      paddingBottom: '0.4rem',
                    }}
                  >
                    <dt style={{ fontSize: '0.8125rem', color: 'var(--ink-soft)' }}>
                      {f.label}
                      {f.autofill && (
                        <span className="field__locked" style={{ marginLeft: 0, display: 'block' }}>
                          ↳ từ hồ sơ
                        </span>
                      )}
                    </dt>
                    <dd style={{ margin: 0, whiteSpace: isTable ? 'normal' : 'pre-wrap', minWidth: 0 }}>
                      {Array.isArray(value) ? (
                        // Trường dạng bảng. Không có nhánh này thì React gặp một
                        // mảng object và trang trắng — lỗi chỉ lộ ra ở đúng đơn
                        // duy nhất có bảng.
                        value.length === 0 ? (
                          '—'
                        ) : (
                          <div className="table-wrap" style={{ maxHeight: 'none' }}>
                          <table className="data-table form-detail-table" style={{ width: "100%" }}>
                            <thead>
                              <tr>
                                <th scope="col">STT</th>
                                {(f.columns ?? []).map((c) => (
                                  <th key={c.key} scope="col">
                                    {c.label}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {value.map((r, i) => (
                                <tr key={i}>
                                  <td>{i + 1}</td>
                                  {(f.columns ?? []).map((c) => (
                                    <td key={c.key}>{r[c.key] || '—'}</td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          </div>
                        )
                      ) : f.type === 'date' && value ? (
                        viDate(`${value}T00:00:00+07:00`)
                      ) : (
                        value || '—'
                      )}
                    </dd>
                  </div>
                );
              })}
            </dl>

            {deletable && (
              <div style={{ marginTop: 'var(--gap-5)', paddingTop: 'var(--gap-4)', borderTop: '1px solid var(--rule-faint)' }}>
                {confirmDelete ? (
                  <div className="row" style={{ gap: 'var(--gap-3)', alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: '0.875rem', color: 'var(--seal)' }}>
                      Xóa hẳn đơn này? Không thể hoàn tác.
                    </span>
                    <button type="button" className="btn btn--danger btn--sm" onClick={onDelete} disabled={busy}>
                      {busy ? 'Đang xóa…' : 'Xác nhận xóa'}
                    </button>
                    <button type="button" className="btn btn--ghost btn--sm" onClick={() => setConfirmDelete(false)} disabled={busy}>
                      Hủy
                    </button>
                  </div>
                ) : (
                  <button type="button" className="btn btn--danger btn--sm" onClick={() => setConfirmDelete(true)}>
                    Xóa đơn
                  </button>
                )}
              </div>
            )}
          </section>
        )}

        {tab === 'noi-nhan' && (
          <section className="sheet sheet--pad">
            <ApprovalFlow
              variant="vertical"
              steps={s.template.approvalFlow.map((step) => ({
                order: step.order,
                title: step.title,
                roleCode: step.roleCode,
              }))}
              currentStepOrder={s.currentStepOrder}
              submissionStatus={s.status}
            />
            <p style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', margin: 'var(--gap-4) 0 0' }}>
              Đơn chỉ chuyển sang cấp sau khi cấp trước đã quyết. Bị trả lại thì đơn quay về trạng
              thái sửa được, và chữ ký cũ bị hủy.
            </p>
          </section>
        )}

        {tab === 'dinh-kem' && (
          <section className="sheet sheet--pad">
            <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--ink-soft)' }}>
              Chưa hỗ trợ đính kèm văn bản cho biểu mẫu này.
            </p>
          </section>
        )}
      </div>

      {/* --------------------------------------------------------- cột phải */}
      <aside className="doc-layout__aside stack">
        <section className="sheet sheet--pad">
          <div className="spread" style={{ marginBottom: 'var(--gap-4)', flexWrap: 'wrap', gap: 'var(--gap-3)' }}>
            <div className="row" style={{ gap: 'var(--gap-3)', flexWrap: 'wrap' }}>
              <h2 className="eyebrow" style={{ margin: 0 }}>
                Bản in
              </h2>
              {s.generatedAt && <span className="tag tag--ok">dựng {viDateTime(s.generatedAt)}</span>}
              {s.signedHash && <span className="tag tag--ok">đã ký</span>}
            </div>
            {s.editable && (
              <div className="row" style={{ gap: 'var(--gap-2)' }}>
                {editableFields.length > 0 && (
                  <button type="button" className="btn btn--ghost btn--sm" onClick={onEdit}>
                    Sửa nội dung
                  </button>
                )}
                <button type="button" className="btn btn--ghost btn--sm" onClick={onRender} disabled={busy}>
                  {busy ? 'Đang lưu…' : s.generatedHash ? 'Lưu lại bản in' : 'Lưu bản in'}
                </button>
                {hasSignature && (
                  <button
                    type="button"
                    className="btn btn--primary btn--sm"
                    onClick={() => setSignOpen((v) => !v)}
                  >
                    Ký đơn
                  </button>
                )}
              </div>
            )}
          </div>

          {s.editable && (
            <SignPanel
              code={s.code}
              busy={busy}
              error={signError}
              hasSignature={hasSignature}
              open={signOpen}
              onClose={() => setSignOpen(false)}
              onSign={onSign}
            />
          )}

          {previewUrl ? (
            <DocumentPreview url={previewUrl} fileName={`${s.code}${s.signedHash ? '' : '-chua-ky'}.docx`} />
          ) : (
            <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--ink-soft)' }}>
              Chưa dựng bản in. Bấm "Lưu bản in" để xem đơn sẽ in ra như thế nào trước khi ký.
            </p>
          )}

          {s.generatedHash && (
            <div className="row" style={{ marginTop: 'var(--gap-4)' }}>
              <a className="btn btn--ghost" href={formsApi.fileUrl(s.id, 'unsigned')}>
                Tải bản chưa ký
              </a>
              {s.signedHash && (
                <a className="btn btn--ghost" href={formsApi.fileUrl(s.id)}>
                  Tải bản đã ký
                </a>
              )}
            </div>
          )}
        </section>

        {s.signedHash && (
          <section className="sheet sheet--pad">
            <h2 className="eyebrow" style={{ marginBottom: 'var(--gap-4)' }}>
              Kiểm chứng chữ ký
            </h2>

            {verification?.signed && (
              <>
                <div
                  className={`notice notice--${verification.matches ? 'ok' : 'error'}`}
                  role="status"
                >
                  {verification.message}
                </div>
                {verification.signings.map((sg, i) => (
                  <dl key={i} style={{ margin: 'var(--gap-4) 0 0', display: 'grid', gap: 'var(--gap-2)', fontSize: '0.75rem' }}>
                    <div className="spread">
                      <dt style={{ color: 'var(--ink-faint)' }}>Ký lúc</dt>
                      <dd className="mono" style={{ margin: 0 }}>{viDateTime(sg.signedAt)}</dd>
                    </div>
                    <div className="spread">
                      <dt style={{ color: 'var(--ink-faint)' }}>Từ địa chỉ</dt>
                      <dd className="mono" style={{ margin: 0 }}>{sg.ipAddress ?? '—'}</dd>
                    </div>
                  </dl>
                ))}
              </>
            )}

            <div className="row" style={{ marginTop: 'var(--gap-5)' }}>
              <button type="button" className="btn btn--ghost" onClick={onRunVerify} disabled={busy}>
                {busy ? 'Đang kiểm…' : 'Kiểm chứng file'}
              </button>
              {/* `editable` đã thành false ngay khi ký — đó là chủ đích. Điều
                  kiện gửi là trạng thái vẫn còn nằm trong tay học viên. */}
              {(s.status === 'DRAFT' || s.status === 'NEEDS_REVISION') && (
                <button type="button" className="btn btn--primary" onClick={onSubmitForApproval} disabled={busy}>
                  Gửi trình ký
                </button>
              )}
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', margin: 'var(--gap-3) 0 0' }}>
              “Kiểm chứng file” băm lại file trên đĩa và so với mã băm ghi lúc ký. Khớp nghĩa là
              file chưa bị đụng vào kể từ khi bạn ký.
            </p>
          </section>
        )}
      </aside>
    </div>
  );
}
