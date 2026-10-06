import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from '@/components/shared/Icon';
import { ApiError } from '@/services/api';
import {
  catalogApi,
  type CourseItem,
  type LecturerItem,
} from '@/services/catalog-api';
import { CourseDialog } from './CourseDialog';
import { ConfirmDeleteDialog } from './Dialogs';

type CourseFilter = 'all' | 'no-lecturer';

/**
 * Tab "Môn học": danh sách môn + lọc theo mã/tên và trạng thái giảng viên +
 * thêm / sửa / xóa. Cột giảng viên hiện thẻ "Chưa phân công" khi chưa gán.
 */
export function CoursesPanel() {
  const [items, setItems] = useState<CourseItem[] | null>(null);
  const [lecturers, setLecturers] = useState<LecturerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<CourseFilter>('all');

  const addBtnRef = useRef<HTMLButtonElement>(null);
  const [form, setForm] = useState<{ mode: 'add' } | { mode: 'edit'; item: CourseItem } | null>(null);
  const [toDelete, setToDelete] = useState<CourseItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteBtnRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, l] = await Promise.all([catalogApi.courses(), catalogApi.lecturers()]);
      setItems(c.items);
      setLecturers(l.items);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không tải được danh sách môn học.');
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

  const visible = useMemo(() => {
    const base = items ?? [];
    const q = search.trim().toLowerCase();
    return base.filter((c) => {
      if (filter === 'no-lecturer' && c.lecturer) return false;
      if (!q) return true;
      return c.code.toLowerCase().includes(q) || c.name.toLowerCase().includes(q);
    });
  }, [items, search, filter]);

  async function confirmDelete() {
    if (!toDelete) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await catalogApi.deleteCourse(toDelete.id);
      setToDelete(null);
      flash('Đã xóa môn học.');
      void load();
    } catch (e) {
      setDeleteError(e instanceof ApiError ? e.message : 'Không xóa được môn học.');
    } finally {
      setDeleting(false);
    }
  }

  const empty = !loading && !error && (items?.length ?? 0) === 0;
  const noMatch = !loading && !error && (items?.length ?? 0) > 0 && visible.length === 0;

  return (
    <div className="stack">
      <div className="row train-toolbar">
        <div className="field train-search">
          <label className="field__label" htmlFor="train-course-search">
            Tìm môn
          </label>
          <div className="train-search__box">
            <Icon name="search" size={16} className="train-search__icon" />
            <input
              id="train-course-search"
              className="field__input"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Mã hoặc tên môn…"
            />
          </div>
        </div>

        <div className="seg" role="group" aria-label="Lọc theo giảng viên">
          <button
            type="button"
            className={`seg__opt${filter === 'all' ? ' seg__opt--on' : ''}`}
            onClick={() => setFilter('all')}
            aria-pressed={filter === 'all'}
          >
            Tất cả
          </button>
          <button
            type="button"
            className={`seg__opt${filter === 'no-lecturer' ? ' seg__opt--on' : ''}`}
            onClick={() => setFilter('no-lecturer')}
            aria-pressed={filter === 'no-lecturer'}
          >
            Chưa có giảng viên
          </button>
        </div>

        <button
          ref={addBtnRef}
          type="button"
          className="btn btn--primary train-add"
          onClick={() => setForm({ mode: 'add' })}
        >
          <Icon name="plus" size={18} />
          Thêm môn
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
            <Icon name="book" size={22} />
          </span>
          <p className="empty__title">Chưa có môn học nào</p>
          <p>Bấm "Thêm môn" để tạo môn đầu tiên.</p>
        </div>
      ) : noMatch ? (
        <div className="empty">
          <span className="empty__icon">
            <Icon name="search" size={22} />
          </span>
          <p className="empty__title">Không tìm thấy môn nào</p>
          <p>Thử đổi từ khóa hoặc bộ lọc.</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <caption>
              {visible.length} môn
            </caption>
            <thead>
              <tr>
                <th>Mã</th>
                <th>Tên môn</th>
                <th className="num">Tín chỉ</th>
                <th>Khoa</th>
                <th>Giảng viên phụ trách</th>
                <th className="num">Buổi</th>
                <th aria-label="Thao tác" />
              </tr>
            </thead>
            <tbody>
              {visible.map((c) => (
                <tr key={c.id}>
                  <td className="mono">{c.code}</td>
                  <td>{c.name}</td>
                  <td className="num">{c.credits}</td>
                  <td>{c.facultyName ?? '—'}</td>
                  <td>
                    {c.lecturer ? (
                      <span title={c.lecturer.email}>{c.lecturer.fullName}</span>
                    ) : (
                      <span className="tag tag--warn">Chưa phân công</span>
                    )}
                  </td>
                  <td className="num">{c.sessionCount}</td>
                  <td className="train-acts">
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => setForm({ mode: 'edit', item: c })}
                      aria-label={`Sửa môn ${c.code}`}
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
                      aria-label={`Xóa môn ${c.code}`}
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
        <CourseDialog
          initial={form.mode === 'edit' ? form.item : null}
          lecturers={lecturers}
          openRef={addBtnRef}
          onClose={() => setForm(null)}
          onSaved={() => {
            setForm(null);
            flash(form.mode === 'edit' ? 'Đã cập nhật môn học.' : 'Đã thêm môn học.');
            void load();
          }}
        />
      )}

      {toDelete && (
        <ConfirmDeleteDialog
          openRef={deleteBtnRef}
          title="Xóa môn học"
          message={`Xóa môn ${toDelete.code} — ${toDelete.name}? Thao tác này không thể hoàn tác.`}
          busy={deleting}
          error={deleteError}
          onConfirm={() => void confirmDelete()}
          onClose={() => setToDelete(null)}
        />
      )}
    </div>
  );
}
