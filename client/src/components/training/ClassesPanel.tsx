import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from '@/components/shared/Icon';
import { ApiError } from '@/services/api';
import { catalogApi, type ClassItem } from '@/services/catalog-api';
import { ClassDialog } from './ClassDialog';
import { ConfirmDeleteDialog } from './Dialogs';
import { PAGE_SIZE, Pager } from '@/components/shared/Pager';

const NONE = '__none__';

/** Chuẩn hóa để tìm không phân biệt hoa thường và dấu. */
const fold = (v: string) => v.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').toLowerCase();

/**
 * Tab "Lớp": danh sách lớp + thêm / sửa / xóa. Số học viên là liên kết mở danh sách học viên
 * của lớp đó (qua `onShowStudents`); "Xếp học viên vào lớp" mở toàn bộ học viên (`onShowStudents('tat-ca')`).
 */
export function ClassesPanel({ onShowStudents }: { onShowStudents: (classId: string) => void }) {
  const [items, setItems] = useState<ClassItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Bộ lọc: tìm theo mã/tên/ngành, khoa, ngành, khóa. Đổi bộ lọc thì về trang 1.
  const [search, setSearch] = useState('');
  const [facultyF, setFacultyF] = useState('');
  const [majorF, setMajorF] = useState('');
  const [cohortF, setCohortF] = useState('');
  const [page, setPage] = useState(1);

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

  const faculties = useMemo(
    () => [...new Set((items ?? []).map((c) => c.faculty).filter((f): f is string => !!f))].sort((a, b) => a.localeCompare(b, 'vi')),
    [items],
  );
  // Ngành gợi ý theo khoa đang chọn (khoa trống = mọi ngành).
  const majors = useMemo(
    () =>
      [
        ...new Set(
          (items ?? [])
            .filter((c) => !facultyF || (facultyF === NONE ? !c.faculty : c.faculty === facultyF))
            .map((c) => c.major)
            .filter((m): m is string => !!m),
        ),
      ].sort((a, b) => a.localeCompare(b, 'vi')),
    [items, facultyF],
  );
  const allMajors = useMemo(
    () => [...new Set((items ?? []).map((c) => c.major).filter((m): m is string => !!m))].sort((a, b) => a.localeCompare(b, 'vi')),
    [items],
  );
  const cohorts = useMemo(
    () => [...new Set((items ?? []).map((c) => c.cohortYear).filter((y): y is number => y != null))].sort((a, b) => b - a),
    [items],
  );

  const visible = useMemo(() => {
    const q = fold(search.trim());
    return (items ?? []).filter((c) => {
      if (facultyF && (facultyF === NONE ? !!c.faculty : c.faculty !== facultyF)) return false;
      if (majorF && c.major !== majorF) return false;
      if (cohortF && String(c.cohortYear) !== cohortF) return false;
      return !q || fold(`${c.code} ${c.name} ${c.major ?? ''}`).includes(q);
    });
  }, [items, search, facultyF, majorF, cohortF]);
  const lastPage = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  const shown = visible.slice((Math.min(page, lastPage) - 1) * PAGE_SIZE, Math.min(page, lastPage) * PAGE_SIZE);
  const filtered = Boolean(search.trim() || facultyF || majorF || cohortF);

  const empty = !loading && !error && (items?.length ?? 0) === 0;
  const noMatch = !loading && !error && (items?.length ?? 0) > 0 && visible.length === 0;

  return (
    <div className="stack">
      {(items?.length ?? 0) > 0 && (
        <div className="row train-toolbar train-filters">
          <div className="field train-search">
            <label className="field__label" htmlFor="train-class-search">
              Tìm lớp
            </label>
            <div className="train-search__box">
              <Icon name="search" size={16} className="train-search__icon" />
              <input
                id="train-class-search"
                className="field__input"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                placeholder="Mã, tên lớp hoặc ngành…"
              />
            </div>
          </div>
          <div className="field train-class-filter">
            <label className="field__label" htmlFor="train-class-f-faculty">
              Khoa
            </label>
            <select
              id="train-class-f-faculty"
              className="field__input"
              value={facultyF}
              onChange={(e) => {
                setFacultyF(e.target.value);
                setMajorF('');
                setPage(1);
              }}
            >
              <option value="">Tất cả khoa</option>
              <option value={NONE}>Chưa xếp khoa</option>
              {faculties.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>
          <div className="field train-class-filter">
            <label className="field__label" htmlFor="train-class-f-major">
              Ngành
            </label>
            <select
              id="train-class-f-major"
              className="field__input"
              value={majorF}
              onChange={(e) => {
                setMajorF(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Tất cả ngành</option>
              {majors.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          <div className="field train-class-filter train-class-filter--sm">
            <label className="field__label" htmlFor="train-class-f-cohort">
              Khóa
            </label>
            <select
              id="train-class-f-cohort"
              className="field__input"
              value={cohortF}
              onChange={(e) => {
                setCohortF(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Tất cả</option>
              {cohorts.map((y) => (
                <option key={y} value={String(y)}>
                  {y}
                </option>
              ))}
            </select>
          </div>
          {filtered && (
            <button
              type="button"
              className="btn btn--quiet"
              onClick={() => {
                setSearch('');
                setFacultyF('');
                setMajorF('');
                setCohortF('');
                setPage(1);
              }}
            >
              Bỏ lọc
            </button>
          )}
        </div>
      )}

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
        <button type="button" className="btn btn--quiet" onClick={() => onShowStudents('nhap')}>
          <Icon name="form" size={18} />
          Nhập từ CSV
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
      ) : noMatch ? (
        <div className="empty">
          <span className="empty__icon">
            <Icon name="search" size={22} />
          </span>
          <p className="empty__title">Không có lớp nào khớp bộ lọc</p>
          <p>Thử đổi từ khóa hoặc bấm "Bỏ lọc".</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <caption>
              {filtered ? `${visible.length} / ${items?.length ?? 0} lớp` : `${items?.length ?? 0} lớp`}
            </caption>
            <thead>
              <tr>
                <th>Mã lớp</th>
                <th>Tên</th>
                <th>Khoa</th>
                <th>Ngành</th>
                <th>Khóa</th>
                <th className="num">Học viên</th>
                <th className="num">Buổi học</th>
                <th aria-label="Thao tác" />
              </tr>
            </thead>
            <tbody>
              {shown.map((c) => (
                <tr key={c.id}>
                  <td className="mono">{c.code}</td>
                  <td>{c.name}</td>
                  <td>{c.faculty ?? '—'}</td>
                  <td>{c.major ?? '—'}</td>
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
      {!loading && !empty && !noMatch && (
        <Pager page={Math.min(page, lastPage)} total={visible.length} onPage={setPage} />
      )}

      {form && (
        <ClassDialog
          initial={form.mode === 'edit' ? form.item : null}
          majors={allMajors}
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
