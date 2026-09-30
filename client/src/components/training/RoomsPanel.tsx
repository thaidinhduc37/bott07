import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Icon } from '@/components/shared/Icon';
import { ApiError } from '@/services/api';
import { roomsApi, type RoomItem, type RoomPayload } from '@/services/rooms-api';
import { ConfirmDeleteDialog } from './Dialogs';
import { RoomTimetableDialog } from './RoomTimetableDialog';

type RoomFilter = 'active' | 'all';

/**
 * Tab "Phòng học": danh sách phòng + tìm kiếm (mã / tòa) + lọc trạng thái +
 * thêm / sửa / xóa + xem lịch phòng.
 *
 * Lỗi 409 `ROOM_IN_USE` khi xóa → hiện nguyên `message` của API trong hộp
 * thoại xác nhận và gợi ý bấm "Sửa" để tắt "Đang sử dụng".
 */
export function RoomsPanel() {
  const [items, setItems] = useState<RoomItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<RoomFilter>('active');

  const addBtnRef = useRef<HTMLButtonElement>(null);
  const [form, setForm] = useState<{ mode: 'add' } | { mode: 'edit'; item: RoomItem } | null>(null);
  const [toDelete, setToDelete] = useState<RoomItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteBtnRef = useRef<HTMLButtonElement>(null);
  const [timetableRoom, setTimetableRoom] = useState<RoomItem | null>(null);
  const timetableBtnRef = useRef<HTMLButtonElement>(null);

  // Debounce ô tìm 300ms trước khi gọi API.
  useEffect(() => {
    const t = window.setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await roomsApi.list({
        activeOnly: filter === 'active',
        search: search || undefined,
      });
      setItems(r.items);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không tải được danh sách phòng.');
    } finally {
      setLoading(false);
    }
  }, [filter, search]);

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
      await roomsApi.remove(toDelete.id);
      setToDelete(null);
      flash('Đã xóa phòng.');
      void load();
    } catch (e) {
      // 409 `ROOM_IN_USE` — giữ hộp thoại mở, hiện nguyên message của API.
      setDeleteError(e instanceof ApiError ? e.message : 'Không xóa được phòng.');
    } finally {
      setDeleting(false);
    }
  }

  // Rỗng: chưa có phòng nào; hoặc có từ khóa/bộ lọc mà không khớp gì (thông báo khác nhau).
  const noResults = !loading && !error && (items?.length ?? 0) === 0;
  const noMatch = noResults && (search !== '' || filter !== 'active');
  const empty = noResults && !noMatch;

  return (
    <div className="stack">
      <div className="row room-toolbar">
        <div className="field room-search">
          <label className="field__label" htmlFor="room-search">
            Tìm phòng
          </label>
          <div className="room-search__box">
            <Icon name="search" size={16} className="room-search__icon" />
            <input
              id="room-search"
              className="field__input"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Mã hoặc tòa nhà…"
            />
          </div>
        </div>

        <div className="seg room-seg" role="group" aria-label="Lọc theo trạng thái">
          <button
            type="button"
            className={`seg__opt${filter === 'active' ? ' seg__opt--on' : ''}`}
            onClick={() => setFilter('active')}
            aria-pressed={filter === 'active'}
          >
            Đang dùng
          </button>
          <button
            type="button"
            className={`seg__opt${filter === 'all' ? ' seg__opt--on' : ''}`}
            onClick={() => setFilter('all')}
            aria-pressed={filter === 'all'}
          >
            Tất cả
          </button>
        </div>

        <button
          ref={addBtnRef}
          type="button"
          className="btn btn--primary room-add"
          onClick={() => setForm({ mode: 'add' })}
        >
          <Icon name="plus" size={18} />
          Thêm phòng
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
            <Icon name="location" size={22} />
          </span>
          <p className="empty__title">Chưa có phòng nào</p>
          <p>Bấm "Thêm phòng" để tạo phòng đầu tiên.</p>
        </div>
      ) : noMatch ? (
        <div className="empty">
          <span className="empty__icon">
            <Icon name="search" size={22} />
          </span>
          <p className="empty__title">Không tìm thấy phòng nào</p>
          <p>Thử đổi từ khóa hoặc bộ lọc.</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <caption>
              {items?.length ?? 0} phòng
            </caption>
            <thead>
              <tr>
                <th>Phòng</th>
                <th>Tòa nhà</th>
                <th className="num">Sức chứa</th>
                <th>Loại</th>
                <th className="num">Đang dùng</th>
                <th>Trạng thái</th>
                <th aria-label="Thao tác" />
              </tr>
            </thead>
            <tbody>
              {items?.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.code}</td>
                  <td>{r.building ?? '—'}</td>
                  <td className="num">{r.capacity != null ? r.capacity : '—'}</td>
                  <td>{r.kind ?? '—'}</td>
                  <td className="num">{r.usageCount}</td>
                  <td>
                    {r.isActive ? (
                      <span className="tag tag--ok">Đang dùng</span>
                    ) : (
                      <span className="tag tag--muted">Ngừng sử dụng</span>
                    )}
                  </td>
                  <td className="room-acts">
                    <button
                      ref={timetableBtnRef}
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => setTimetableRoom(r)}
                      aria-label={`Lịch phòng ${r.code}`}
                    >
                      <Icon name="calendar" size={15} />
                      <span className="sr-only">Lịch phòng</span>
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => setForm({ mode: 'edit', item: r })}
                      aria-label={`Sửa phòng ${r.code}`}
                    >
                      <Icon name="pencil" size={15} />
                      <span className="sr-only">Sửa</span>
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => {
                        setDeleteError(null);
                        setToDelete(r);
                      }}
                      aria-label={`Xóa phòng ${r.code}`}
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
        <RoomFormDialog
          initial={form.mode === 'edit' ? form.item : null}
          openRef={addBtnRef}
          onClose={() => setForm(null)}
          onSaved={() => {
            setForm(null);
            flash(form.mode === 'edit' ? 'Đã cập nhật phòng.' : 'Đã thêm phòng.');
            void load();
          }}
        />
      )}

      {toDelete && (
        <ConfirmDeleteDialog
          openRef={deleteBtnRef}
          title="Xóa phòng"
          message={`Xóa phòng ${toDelete.code}${toDelete.building ? ` — ${toDelete.building}` : ''}? Thao tác này không thể hoàn tác.`}
          busy={deleting}
          error={deleteError}
          onConfirm={() => void confirmDelete()}
          onClose={() => setToDelete(null)}
        />
      )}

      {timetableRoom && (
        <RoomTimetableDialog
          room={timetableRoom}
          openRef={timetableBtnRef}
          onClose={() => setTimetableRoom(null)}
        />
      )}
    </div>
  );
}

/**
 * Form thêm / sửa phòng. Khi `initial` có giá trị là chế độ sửa: mã + tòa nhà
 * bị khóa nếu phòng đã có lịch (`usageCount > 0`), và thêm công tắc "Đang sử dụng".
 *
 * Lỗi 409 `ROOM_TAKEN` (mã trùng) hiện nguyên `message` của API.
 */
function RoomFormDialog({
  initial,
  openRef,
  onClose,
  onSaved,
}: {
  initial: RoomItem | null;
  openRef: React.RefObject<HTMLElement | null>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const editing = initial != null;
  const locked = editing && (initial?.usageCount ?? 0) > 0;

  const [code, setCode] = useState(initial?.code ?? '');
  const [building, setBuilding] = useState(initial?.building ?? '');
  const [capacity, setCapacity] = useState(initial?.capacity != null ? String(initial.capacity) : '');
  const [kind, setKind] = useState(initial?.kind ?? '');
  const [note, setNote] = useState(initial?.note ?? '');
  const [isActive, setIsActive] = useState(initial?.isActive ?? true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    dialogRef.current?.showModal();
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (saving) return;
    const cap = capacity.trim() === '' ? null : Number(capacity);
    if (cap !== null && (!Number.isInteger(cap) || cap < 1)) {
      setError('Sức chứa phải là số nguyên từ 1 trở lên.');
      return;
    }
    setSaving(true);
    setError(null);
    const payload: RoomPayload = {
      code: code.trim(),
      building: building.trim() || null,
      capacity: cap,
      kind: kind.trim() || null,
      note: note.trim() || null,
    };
    try {
      if (editing && initial) {
        // Chế độ sửa: mã + tòa nhà chỉ gửi khi không bị khóa; kèm `isActive`.
        if (!locked) {
          payload.code = code.trim();
          payload.building = building.trim() || null;
        }
        payload.isActive = isActive;
        await roomsApi.update(initial.id, payload);
      } else {
        await roomsApi.create(payload);
      }
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không lưu được phòng.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="room-dlg"
      aria-labelledby="room-form-title"
      onClose={onClose}
    >
      <div className="room-dlg__bar">
        <h2 id="room-form-title" className="room-dlg__title">
          {editing ? 'Sửa phòng' : 'Thêm phòng'}
        </h2>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          onClick={() => dialogRef.current?.close()}
          aria-label="Đóng hộp thoại"
        >
          <Icon name="close" size={16} />
          <span className="sr-only">Đóng</span>
        </button>
      </div>
      <div className="room-dlg__body">
        <form onSubmit={(e) => void submit(e)}>
          <div className="field">
            <label className="field__label" htmlFor="room-code">
              Mã phòng<span className="req">*</span>
            </label>
            <input
              id="room-code"
              className="field__input"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              disabled={locked}
              required
              placeholder="VD: A201"
            />
            {locked && (
              <span className="field__hint">
                Phòng đã có lịch nên không đổi tên được — hãy ngừng sử dụng và tạo phòng mới.
              </span>
            )}
          </div>

          <div className="field">
            <label className="field__label" htmlFor="room-building">
              Tòa nhà
            </label>
            <input
              id="room-building"
              className="field__input"
              value={building}
              onChange={(e) => setBuilding(e.target.value)}
              disabled={locked}
              placeholder="VD: Tòa A"
            />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="room-capacity">
              Sức chứa
            </label>
            <input
              id="room-capacity"
              className="field__input"
              type="number"
              min={1}
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
              placeholder="VD: 60"
            />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="room-kind">
              Loại
            </label>
            <input
              id="room-kind"
              className="field__input"
              list="room-kind-list"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              placeholder="VD: Lý thuyết"
            />
            <datalist id="room-kind-list">
              <option value="Lý thuyết" />
              <option value="Thực hành" />
              <option value="Hội trường" />
              <option value="Phòng thi" />
            </datalist>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="room-note">
              Ghi chú
            </label>
            <textarea
              id="room-note"
              className="field__input"
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Ghi chú về phòng…"
            />
          </div>

          {editing && (
            <label className="room-switch">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
              />
              <span className="room-switch__label">Đang sử dụng</span>
            </label>
          )}

          {error && (
            <p className="notice notice--error" role="alert">
              {error}
            </p>
          )}

          <div className="room-dlg__actions">
            <button type="submit" className="btn btn--primary" disabled={saving}>
              {saving ? 'Đang lưu…' : editing ? 'Lưu thay đổi' : 'Thêm phòng'}
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
      </div>
    </dialog>
  );
}
