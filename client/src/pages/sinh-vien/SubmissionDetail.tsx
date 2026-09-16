import { useNavigate, useParams } from 'react-router-dom';
import { STATUS_TAG } from '@/services/forms-api';
import { useSubmissionDetail } from '@/hooks/useSubmissionDetail';
import { SubmissionForm } from '@/components/forms/SubmissionForm';
import { SubmissionDetailView } from '@/components/forms/SubmissionDetailView';
import { ComposerChrome } from '@/components/forms/ComposerChrome';

const CLOSE_TO = '/sinh-vien/bieu-mau';

/**
 * Xem/soạn một đơn — khung soạn thảo toàn màn hình (`ComposerChrome`), không
 * phải trang con nằm trong sidebar. Xem docstring của `ComposerChrome` cho
 * lý do; đây là chỗ duy nhất còn dùng `useSubmissionDetail` trực tiếp — bar
 * tiêu đề cần biết tên đơn/trạng thái NGAY TỪ LÚC đang tải, nên hook phải
 * sống ở đây thay vì trong một panel con.
 */
export default function SubmissionDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const {
    s,
    loading,
    editing,
    setEditing,
    busy,
    error,
    flash,
    fieldErrors,
    hasSignature,
    signError,
    verification,
    sign,
    submitForApproval,
    runVerify,
    save,
    render,
    remove,
  } = useSubmissionDetail(id);

  async function handleDelete() {
    if (await remove()) navigate(CLOSE_TO);
  }

  if (loading) {
    return (
      <ComposerChrome title="Đang tải…" closeTo={CLOSE_TO}>
        <p className="eyebrow">Đang tải…</p>
      </ComposerChrome>
    );
  }

  if (!s) {
    return (
      <ComposerChrome title="Không tìm thấy đơn" closeTo={CLOSE_TO}>
        <div className="notice notice--error" role="alert">
          {error ?? 'Không tìm thấy đơn'}
        </div>
      </ComposerChrome>
    );
  }

  const editableFields = s.template.fields.filter((f) => !f.autofill);

  return (
    <ComposerChrome
      title={s.template.name}
      subtitle={s.code}
      statusTag={<span className={`tag ${STATUS_TAG[s.status]}`}>{s.statusLabel}</span>}
      closeTo={CLOSE_TO}
    >
      <div className="stack">
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

        {!s.editable &&
          (s.signedHash && (s.status === 'DRAFT' || s.status === 'NEEDS_REVISION') ? (
            <div className="notice notice--info">
              Nội dung đơn đã khóa từ lúc bạn ký. Chữ ký gắn với đúng nội dung tại thời điểm ký,
              nên sửa được nội dung sau đó thì chữ ký không còn chứng minh gì. Cần đổi nội dung
              thì lập đơn mới.
            </div>
          ) : (
            <div className="notice notice--info">
              Nội dung đơn đã khóa từ lúc gửi trình ký. Bản người duyệt đọc và bản bạn đã ký phải
              là một — nếu cần sửa, người duyệt sẽ chuyển đơn về trạng thái “Yêu cầu bổ sung”.
            </div>
          ))}

        {editing ? (
          <SubmissionForm
            fields={s.template.fields}
            templateCode={s.template.code}
            autofill={s.profileSnapshot}
            initial={s.formData}
            busy={busy}
            submitLabel="Lưu thay đổi"
            fieldErrors={fieldErrors}
            onSubmit={save}
            onCancel={() => setEditing(false)}
          />
        ) : (
          <SubmissionDetailView
            s={s}
            busy={busy}
            editableFields={editableFields}
            hasSignature={hasSignature}
            signError={signError}
            verification={verification}
            onSign={sign}
            onEdit={() => setEditing(true)}
            onRender={render}
            onRunVerify={runVerify}
            onSubmitForApproval={submitForApproval}
            onDelete={handleDelete}
          />
        )}
      </div>
    </ComposerChrome>
  );
}
