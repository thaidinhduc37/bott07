import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Icon } from '@/components/shared/Icon';
import { ApiError } from '@/services/api';
import { catalogApi, type ClassItem } from '@/services/catalog-api';

/**
 * Hộp thoại dùng chung cho trang Quản lý đào tạo.
 *
 * Dùng `<dialog>` gốc với `showModal()`: Esc đóng, focus tự bị giữ trong dialog
 * và trả về nút đã mở khi đóng (giống `EntryDetail`). Nút mở được truyền qua
 * `openRef` để focus trả về đúng chỗ.
 */

/** Khung hộp thoại căn giữa: tiêu đề + nút đóng + thân. */
export function TrainingDialog({
  openRef,
  title,
  titleId,
  onClose,
  children,
  forwardRef,
}: {
  openRef: React.RefObject<HTMLElement | null>;
  title: string;
  titleId: string;
  onClose: () => void;
  children: ReactNode;
  /** Ref để form bên trong tự đóng dialog khi bấm "Hủy". */
  forwardRef?: React.RefObject<HTMLDialogElement | null>;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = dialogRef.current;
    if (d && !d.open) d.showModal();
    // Trả focus về nút mở khi đóng (bấm backdrop, Esc, hay nút đóng).
    const onClosed = () => openRef.current?.focus();
    d?.addEventListener('close', onClosed);
    return () => d?.removeEventListener('close', onClosed);
  }, [openRef]);

  const close = useCallback(() => dialogRef.current?.close(), []);

  return (
    <dialog
      ref={(el) => {
        dialogRef.current = el;
        if (forwardRef) forwardRef.current = el;
      }}
      className="train-dlg"
      aria-labelledby={titleId}
      onClose={onClose}
    >
      <div className="train-dlg__bar">
        <h2 id={titleId} className="train-dlg__title">
          {title}
        </h2>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          onClick={close}
          aria-label="Đóng hộp thoại"
        >
          <Icon name="close" size={16} />
          <span className="sr-only">Đóng</span>
        </button>
      </div>
      <div className="train-dlg__body">{children}</div>
    </dialog>
  );
}

/**
 * Hộp thoại xác nhận xóa (lớp / môn). Lỗi 409 (đang dùng) hiện nguyên
 * `message` của API trong hộp thoại, không đóng — người dùng thấy lý do.
 */
export function ConfirmDeleteDialog({
  openRef,
  title,
  message,
  busy,
  error,
  onConfirm,
  onClose,
}: {
  openRef: React.RefObject<HTMLElement | null>;
  title: string;
  message: string;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <TrainingDialog
      openRef={openRef}
      title={title}
      titleId="train-confirm-title"
      onClose={onClose}
    >
      <p className="train-confirm__msg">{message}</p>
      {error && (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      )}
      <div className="train-dlg__actions">
        <button
          type="button"
          className="btn btn--danger"
          disabled={busy}
          onClick={onConfirm}
        >
          {busy ? 'Đang xóa…' : 'Xóa'}
        </button>
        <button type="button" className="btn btn--ghost" disabled={busy} onClick={onClose}>
          Hủy
        </button>
      </div>
    </TrainingDialog>
  );
}

/**
 * Hộp thoại đổi lớp cho một học viên. Chọn một lớp hoặc "Bỏ lớp" để tách học
 * viên ra khỏi mọi lớp.
 */
export function AssignClassDialog({
  student,
  classes,
  openRef,
  onClose,
  onSaved,
}: {
  student: { id: string; fullName: string; studentCode: string; class: { id: string } | null };
  classes: ClassItem[];
  openRef: React.RefObject<HTMLElement | null>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [classId, setClassId] = useState(student.class?.id ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  async function submit() {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      await catalogApi.setStudentClass(student.id, classId || null);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không đổi được lớp.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <TrainingDialog
      openRef={openRef}
      title={`Đổi lớp — ${student.fullName}`}
      titleId="train-assign-title"
      onClose={onClose}
      forwardRef={dialogRef}
    >
      <p className="train-assign__who mono">{student.studentCode}</p>
      <div className="field">
        <label className="field__label" htmlFor="train-assign-class">
          Lớp
        </label>
        <select
          id="train-assign-class"
          className="field__input"
          value={classId}
          onChange={(e) => setClassId(e.target.value)}
        >
          <option value="">— Bỏ lớp —</option>
          {classes.map((c) => (
            <option key={c.id} value={c.id}>
              {c.code} — {c.name}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      )}

      <div className="train-dlg__actions">
        <button type="button" className="btn btn--primary" disabled={saving} onClick={() => void submit()}>
          {saving ? 'Đang lưu…' : 'Lưu'}
        </button>
        <button type="button" className="btn btn--ghost" disabled={saving} onClick={onClose}>
          Hủy
        </button>
      </div>
    </TrainingDialog>
  );
}
