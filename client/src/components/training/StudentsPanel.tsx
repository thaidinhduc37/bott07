import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '@/components/shared/Icon';
import { API_URL, ApiError } from '@/services/api';
import {
  catalogApi,
  type ClassItem,
  type StudentItem,
} from '@/services/catalog-api';
import { AssignClassDialog } from './Dialogs';

const PAGE_SIZE = 50;

type StudentFilter = 'all' | 'unassigned';

/**
 * Tab "Học viên": lọc theo lớp / tìm kiếm (debounce 300ms) / chưa có lớp,
 * phân trang 50, chọn hàng + xếp hàng loạt vào lớp, và đổi lớp từng người.
 *
 * `initialClassId` — khi được đặt (đi từ tab Lớp), lọc sẵn theo lớp đó.
 */
export function StudentsPanel({ initialClassId }: { initialClassId?: string }) {
  const [items, setItems] = useState<StudentItem[] | null>(null);
  const [classes, setClasses] = useState<ClassItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [classId, setClassId] = useState(initialClassId ?? '');
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<StudentFilter>('all');

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkClass, setBulkClass] = useState('');
  const [bulkBusy, setBulkBusy] = useState(false);

  const [assigning, setAssigning] = useState<StudentItem | null>(null);
  const assignBtnRef = useRef<HTMLButtonElement>(null);

  // Danh sách lớp để dùng cho bộ lọc và hộp thoại đổi lớp.
  useEffect(() => {
    catalogApi
      .classes()
      .then((r) => setClasses(r.items))
      .catch(() => setClasses([]));
  }, []);

  // Debounce ô tìm 300ms trước khi gọi API.
  useEffect(() => {
    const t = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await catalogApi.students({
        classId: classId || undefined,
        search: search || undefined,
        unassigned: filter === 'unassigned' || undefined,
        page,
        pageSize: PAGE_SIZE,
      });
      setItems(r.items);
      setTotal(r.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không tải được danh sách học viên.');
    } finally {
      setLoading(false);
    }
  }, [classId, search, filter, page]);

  useEffect(() => {
    void load();
  }, [load]);

  // Đổi bộ lọc / lớp / tìm → về trang 1 và bỏ chọn.
  function resetPage() {
    setPage(1);
    setSelected(new Set());
  }

  function flash(msg: string) {
    setNotice(msg);
    window.setTimeout(() => setNotice(null), 5000);
  }

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function toggleOne(id: string, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  const allOnPageSelected =
    (items?.length ?? 0) > 0 && items!.every((s) => selected.has(s.id));

  function toggleAllOnPage(checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const s of items ?? []) {
        if (checked) next.add(s.id);
        else next.delete(s.id);
      }
      return next;
    });
  }

  async function runBulkAssign() {
    if (!bulkClass || selected.size === 0 || bulkBusy) return;
    setBulkBusy(true);
    setError(null);
    try {
      const r = await catalogApi.assignClass(bulkClass, [...selected]);
      const n = r.updated;
      const m = r.skipped;
      flash(
        m > 0
          ? `Đã xếp ${n} học viên, bỏ qua ${m}.`
          : `Đã xếp ${n} học viên.`,
      );
      setSelected(new Set());
      setBulkClass('');
      void load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không xếp được học viên vào lớp.');
    } finally {
      setBulkBusy(false);
    }
  }

  const empty = !loading && !error && (items?.length ?? 0) === 0;

  return (
    <div className="stack">
      <div className="row train-toolbar train-toolbar--students">
        <div className="field train-class-filter">
          <label className="field__label" htmlFor="train-student-class">
            Lớp
          </label>
          <select
            id="train-student-class"
            className="field__input"
            value={classId}
            onChange={(e) => {
              setClassId(e.target.value);
              resetPage();
            }}
          >
            <option value="">Tất cả lớp</option>
            {classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} — {c.name}
              </option>
            ))}
          </select>
        </div>

        <div className="field train-search">
          <label className="field__label" htmlFor="train-student-search">
            Tìm học viên
          </label>
          <div className="train-search__box">
            <Icon name="search" size={16} className="train-search__icon" />
            <input
              id="train-student-search"
              className="field__input"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Mã, tên hoặc email…"
            />
          </div>
        </div>

        <div className="seg train-seg" role="group" aria-label="Lọc theo lớp">
          <button
            type="button"
            className={`seg__opt${filter === 'all' ? ' seg__opt--on' : ''}`}
            onClick={() => {
              setFilter('all');
              resetPage();
            }}
            aria-pressed={filter === 'all'}
          >
            Tất cả
          </button>
          <button
            type="button"
            className={`seg__opt${filter === 'unassigned' ? ' seg__opt--on' : ''}`}
            onClick={() => {
              setFilter('unassigned');
              resetPage();
            }}
            aria-pressed={filter === 'unassigned'}
          >
            Chưa có lớp
          </button>
        </div>

        <a
          className="btn btn--quiet train-export"
          href={`${API_URL}/catalog/students/export${classId ? `?classId=${classId}` : ''}`}
        >
          <Icon name="form" size={16} />
          Tải CSV {classId ? 'lớp này' : 'tất cả'}
        </a>
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

      {/* Thanh hành động hàng loạt — chỉ hiện khi có hàng được chọn. */}
      {selected.size > 0 && (
        <div className="train-bulk" role="region" aria-label="Xếp học viên vào lớp">
          <span className="train-bulk__count">
            Đã chọn {selected.size} học viên
          </span>
          <label className="field train-bulk__field">
            <span className="field__label">Xếp vào lớp</span>
            <select
              className="field__input"
              value={bulkClass}
              onChange={(e) => setBulkClass(e.target.value)}
            >
              <option value="">— chọn lớp —</option>
              {classes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn--primary"
            disabled={bulkBusy || !bulkClass}
            onClick={() => void runBulkAssign()}
          >
            {bulkBusy ? 'Đang xếp…' : 'Xếp vào lớp'}
          </button>
          <button
            type="button"
            className="btn btn--ghost"
            disabled={bulkBusy}
            onClick={() => setSelected(new Set())}
          >
            Bỏ chọn
          </button>
        </div>
      )}

      {loading ? (
        <p className="eyebrow">Đang tải…</p>
      ) : empty ? (
        <div className="empty">
          <span className="empty__icon">
            <Icon name="users" size={22} />
          </span>
          <p className="empty__title">Không có học viên nào</p>
          <p>Thử đổi bộ lọc lớp hoặc từ khóa tìm kiếm.</p>
        </div>
      ) : (
        <>
          <div className="table-wrap">
            <table className="data-table">
              <caption>
                {total} học viên
              </caption>
              <thead>
                <tr>
                  <th aria-label="Chọn">
                    <input
                      type="checkbox"
                      aria-label="Chọn tất cả học viên trong trang"
                      checked={allOnPageSelected}
                      onChange={(e) => toggleAllOnPage(e.target.checked)}
                    />
                  </th>
                  <th>Mã HV</th>
                  <th>Họ tên</th>
                  <th>Email</th>
                  <th>Lớp</th>
                  <th aria-label="Thao tác" />
                </tr>
              </thead>
              <tbody>
                {items?.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Chọn học viên ${s.fullName}`}
                        checked={selected.has(s.id)}
                        onChange={(e) => toggleOne(s.id, e.target.checked)}
                      />
                    </td>
                    <td className="mono">{s.studentCode}</td>
                    <td>{s.fullName}</td>
                    <td>{s.email}</td>
                    <td>
                      {s.class ? (
                        <span className="mono">{s.class.code}</span>
                      ) : (
                        <span className="tag tag--warn">Chưa có lớp</span>
                      )}
                    </td>
                    <td className="train-acts">
                      <button
                        ref={assignBtnRef}
                        type="button"
                        className="btn btn--ghost btn--sm"
                        onClick={() => setAssigning(s)}
                        aria-label={`Đổi lớp cho ${s.fullName}`}
                      >
                        <Icon name="pencil" size={15} />
                        <span className="sr-only">Đổi lớp</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Phân trang */}
          {pages > 1 && (
            <nav className="train-pager" aria-label="Phân trang">
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Trước
              </button>
              <span className="train-pager__info mono">
                Trang {page} / {pages}
              </span>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                disabled={page >= pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Sau
              </button>
            </nav>
          )}
        </>
      )}

      {assigning && (
        <AssignClassDialog
          student={assigning}
          classes={classes}
          openRef={assignBtnRef}
          onClose={() => setAssigning(null)}
          onSaved={() => {
            setAssigning(null);
            flash('Đã cập nhật lớp của học viên.');
            void load();
          }}
        />
      )}
    </div>
  );
}
