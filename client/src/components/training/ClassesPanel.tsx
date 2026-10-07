import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '@/components/shared/Icon';
import { ApiError } from '@/services/api';
import { catalogApi, type ClassItem } from '@/services/catalog-api';
import { ClassDialog } from './ClassDialog';
import { ConfirmDeleteDialog } from './Dialogs';

/**
 * Tab "Lớp": danh sách lớp + thêm / sửa / xóa. Số học viên là liên kết mở danh sách học viên
 * của lớp đó (qua `onShowStudents`); "Xếp học viên vào lớp" mở toàn bộ học viên (`onShowStudents('tat-ca')`).
 */
export function ClassesPanel({ onShowStudents }: { onShowStudents: (classId: string) => void }) {
  const [items, setItems] = useState<ClassItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Nút mở hộp thoại — để trả focus về đúng chỗ khi đóng.
  const addBtnRef = useRef<HTMLButtonElement>(null);
  const [form, setForm] = useState<{ mode: 'add' } | { mode: 'edit'; item: ClassItem } | null>(null);
  const [toDelete, setToDelete] = useState<ClassItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteBtnRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await catalogApi.classes();
      setItems(r.items);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không tải được danh sách lớp.');
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
      await catalogApi.deleteClass(toDelete.id);
      setToDelete(null);
      flash('Đã xóa lớp.');
      void load();
    } catch (e) {
      // 409 (lớp đang dùng) — giữ hộp thoại mở, hiện nguyên message của API.
      setDeleteError(e instanceof ApiError ? e.message : 'Không xóa được lớp.');
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
          Thêm lớp
        </button>
        <button type="button" className="btn btn--quiet" onClick={() => onShowStudents('tat-ca')}>
          <Icon name="users" size={18} />
          Xếp học viên vào lớp
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
            <Icon name="users" size={22} />
          </span>
          <p className="empty__title">Chưa có lớp nào</p>
          <p>Bấm "Thêm lớp" để tạo lớp đầu tiên.</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <caption>
              {items?.length ?? 0} lớp
            </caption>
            <thead>
              <tr>
                <th>Mã lớp</th>
                <th>Tên</th>
                <th>Khoa</th>
                <th>Khóa</th>
                <th className="num">Học viên</th>
                <th className="num">Buổi học</th>
                <th aria-label="Thao tác" />
              </tr>
            </thead>
            <tbody>
              {items?.map((c) => (
                <tr key={c.id}>
                  <td className="mono">{c.code}</td>
                  <td>{c.name}</td>
                  <td>{c.faculty ?? '—'}</td>
                  <td className="mono">{c.cohortYear ?? '—'}</td>
                  <td className="num">
                    <button
                      type="button"
                      className="btn--quiet train-count-link"
                      onClick={() => onShowStudents(c.id)}
                      aria-label={`Xem ${c.studentCount} học viên của lớp ${c.code}`}
                    >
                      {c.studentCount}
                    </button>
                  </td>
                  <td className="num">{c.sessionCount}</td>
                  <td className="train-acts">
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => setForm({ mode: 'edit', item: c })}
                      aria-label={`Sửa lớp ${c.code}`}
                    >
                      <Icon name="pencil" size={15} />
                      <span className="sr-only">Sửa</span>
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => {
                        setDeleteError(null);
                        setToDelete(c);
                      }}
                      aria-label={`Xóa lớp ${c.code}`}
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
        <ClassDialog
          initial={form.mode === 'edit' ? form.item : null}
          openRef={addBtnRef}
          onClose={() => setForm(null)}
          onSaved={() => {
            setForm(null);
            flash(form.mode === 'edit' ? 'Đã cập nhật lớp.' : 'Đã thêm lớp.');
            void load();
          }}
        />
      )}

      {toDelete && (
        <ConfirmDeleteDialog
          openRef={deleteBtnRef}
          title="Xóa lớp"
          message={`Xóa lớp ${toDelete.code} — ${toDelete.name}? Thao tác này không thể hoàn tác.`}
          busy={deleting}
          error={deleteError}
          onConfirm={() => void confirmDelete()}
          onClose={() => setToDelete(null)}
        />
      )}
    </div>
  );
}
