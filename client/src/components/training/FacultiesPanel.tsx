import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '@/components/shared/Icon';
import { ApiError } from '@/services/api';
import {
  facultyApi,
  type FacultyItem,
  type HeadCandidate,
} from '@/services/faculty-api';
import { ConfirmDeleteDialog, TrainingDialog } from './Dialogs';

/**
 * Tab "Khoa" (ADMIN / ACADEMIC_MANAGER): danh sách khoa + thêm / sửa / xóa.
 * Bấm tên khoa hoặc "Chi tiết" mở FacultyDetail (qua `onOpenDetail`).
 */
export function FacultiesPanel({ onOpenDetail }: { onOpenDetail: (id: string) => void }) {
  const [items, setItems] = useState<FacultyItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const addBtnRef = useRef<HTMLButtonElement>(null);
  const [form, setForm] = useState<{ mode: 'add' } | { mode: 'edit'; item: FacultyItem } | null>(null);
  const [toDelete, setToDelete] = useState<FacultyItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteBtnRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await facultyApi.list();
      setItems(r.items);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không tải được danh sách khoa.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function flash(msg: string) {
    setNotice(msg);
    window.setTimeout(() => setNotice(null), 4000);
  }

  async function confirmDelete() {
    if (!toDelete) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await facultyApi.remove(toDelete.id);
      setToDelete(null);
      flash('Đã xóa khoa.');
      void load();
    } catch (e) {
      setDeleteError(e instanceof ApiError ? e.message : 'Không xóa được khoa.');
    } finally {
      setDeleting(false);
    }
  }

  const empty = !loading && !error && (items?.length ?? 0) === 0;

  return (
    <div className="stack">
      <div className="row train-toolbar">
        <button
          ref={addBtnRef}
          type="button"
          className="btn btn--primary"
          onClick={() => setForm({ mode: 'add' })}
        >
          <Icon name="plus" size={18} />
          Thêm khoa
        </button>
      </div>

      {notice && (
        <div className="notice notice--ok" role="status">
          {notice}
        </div>
      )}

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <p className="eyebrow">Đang tải…</p>
      ) : empty ? (
        <div className="empty">
          <span className="empty__icon">
            <Icon name="folder" size={22} />
          </span>
          <p className="empty__title">Chưa có khoa nào</p>
          <p>Bấm "Thêm khoa" để tạo khoa đầu tiên.</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <caption>
              {items?.length ?? 0} khoa
            </caption>
            <thead>
              <tr>
                <th>Mã khoa</th>
                <th>Tên khoa</th>
                <th>Trưởng khoa</th>
                <th className="num">Lớp</th>
                <th className="num">Môn</th>
                <th className="num">GV</th>
                <th className="num">HV</th>
                <th aria-label="Thao tác" />
              </tr>
            </thead>
            <tbody>
              {items?.map((f) => (
                <tr key={f.id}>
                  <td className="mono">{f.code}</td>
                  <td>
                    <button
                      type="button"
                      className="btn--quiet train-count-link"
                      onClick={() => onOpenDetail(f.id)}
                      aria-label={`Xem chi tiết khoa ${f.name}`}
                    >
                      {f.name}
                    </button>
                  </td>
                  <td>
                    {f.head ? (
                      <span title={f.head.email}>{f.head.fullName}</span>
                    ) : (
                      <span className="tag tag--warn">Chưa có</span>
                    )}
                  </td>
                  <td className="num">{f.classCount}</td>
                  <td className="num">{f.courseCount}</td>
                  <td className="num">{f.lecturerCount}</td>
                  <td className="num">{f.studentCount}</td>
                  <td className="train-acts">
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => onOpenDetail(f.id)}
                      aria-label={`Chi tiết khoa ${f.code}`}
                    >
                      <Icon name="arrow" size={15} />
                      <span className="sr-only">Chi tiết</span>
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => setForm({ mode: 'edit', item: f })}
                      aria-label={`Sửa khoa ${f.code}`}
                    >
                      <Icon name="pencil" size={15} />
                      <span className="sr-only">Sửa</span>
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => {
                        setDeleteError(null);
                        setToDelete(f);
                      }}
                      aria-label={`Xóa khoa ${f.code}`}
                    >
                      <Icon name="trash" size={15} />
                      <span className="sr-only">Xóa</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {form && (
        <FacultyDialog
          initial={form.mode === 'edit' ? form.item : null}
          openRef={addBtnRef}
          onClose={() => setForm(null)}
          onSaved={() => {
            setForm(null);
            flash(form.mode === 'edit' ? 'Đã cập nhật khoa.' : 'Đã thêm khoa.');
            void load();
          }}
        />
      )}

      {toDelete && (
        <ConfirmDeleteDialog
          openRef={deleteBtnRef}
          title="Xóa khoa"
          message={`Xóa khoa ${toDelete.code} — ${toDelete.name}? Thao tác này không thể hoàn tác.`}
          busy={deleting}
          error={deleteError}
          onConfirm={() => void confirmDelete()}
          onClose={() => setToDelete(null)}
        />
      )}
    </div>
  );
}

/**
 * Hộp thoại thêm / sửa khoa. Ô "Trưởng khoa" là `<select>` từ
 * `GET /faculties/head-candidates`, có tùy chọn "— Chưa có —".
 */
function FacultyDialog({
  initial,
  openRef,
  onClose,
  onSaved,
}: {
  initial: FacultyItem | null;
  openRef: React.RefObject<HTMLElement | null>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [code, setCode] = useState(initial?.code ?? '');
  const [name, setName] = useState(initial?.name ?? '');
  const [headId, setHeadId] = useState(initial?.head?.id ?? '');
  const [heads, setHeads] = useState<HeadCandidate[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  const editing = initial != null;

  useEffect(() => {
    facultyApi
      .headCandidates()
      .then((r) => setHeads(r.items))
      .catch(() => setHeads([]));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (saving) return;
    setSaving(true);
    setError(null);
    const payload = {
      code: code.trim(),
      name: name.trim(),
      headId: headId || null,
    };
    try {
      if (editing && initial) {
        await facultyApi.update(initial.id, payload);
      } else {
        await facultyApi.create(payload);
      }
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không lưu được khoa.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <TrainingDialog
      openRef={openRef}
      title={editing ? 'Sửa khoa' : 'Thêm khoa'}
      titleId="train-faculty-title"
      onClose={onClose}
      forwardRef={dialogRef}
    >
      <form onSubmit={(e) => void submit(e)}>
        <div className="field">
          <label className="field__label" htmlFor="train-faculty-code">
            Mã khoa<span className="req">*</span>
          </label>
          <input
            id="train-faculty-code"
            className="field__input"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            disabled={editing}
            required
            placeholder="VD: CNTT"
          />
          {editing && (
            <span className="field__hint">Mã khoa không thể đổi sau khi đã tạo.</span>
          )}
        </div>

        <div className="field">
          <label className="field__label" htmlFor="train-faculty-name">
            Tên khoa<span className="req">*</span>
          </label>
          <input
            id="train-faculty-name"
            className="field__input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="VD: Khoa Công nghệ thông tin"
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="train-faculty-head">
            Trưởng khoa
          </label>
          <select
            id="train-faculty-head"
            className="field__input"
            value={headId}
            onChange={(e) => setHeadId(e.target.value)}
          >
            <option value="">— Chưa có —</option>
            {heads.map((h) => (
              <option key={h.id} value={h.id}>
                {h.fullName}
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
          <button type="submit" className="btn btn--primary" disabled={saving}>
            {saving ? 'Đang lưu…' : editing ? 'Lưu thay đổi' : 'Thêm khoa'}
          </button>
          <button
            type="button"
            className="btn btn--ghost"
            disabled={saving}
            onClick={() => dialogRef.current?.close()}
          >
            Hủy
          </button>
        </div>
      </form>
    </TrainingDialog>
  );
}
