import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from '@/components/shared/Icon';
import { ApiError } from '@/services/api';
import { roomsApi, type RoomItem, type RoomTimetable } from '@/services/rooms-api';
import { dateOf, isoDate, timeOf, weekdayOf } from '@/services/schedule-api';

/**
 * Lịch phòng trong khoảng ngày — nhóm theo ngày, mỗi dòng: giờ · môn · lớp ·
 * thẻ Thi/Học. Rỗng → "Phòng trống trong khoảng này".
 *
 * Dùng `<dialog>` gốc với `showModal()`; Esc đóng, focus trả về nút đã mở.
 */
export function RoomTimetableDialog({
  room,
  openRef,
  onClose,
}: {
  room: RoomItem;
  openRef: React.RefObject<HTMLElement | null>;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  // Khoảng mặc định: hôm nay → +14 ngày (giờ Việt Nam).
  const [from, setFrom] = useState(() => isoDate(new Date()));
  const [to, setTo] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 14);
    return isoDate(d);
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<RoomTimetable | null>(null);

  const load = useCallback(async () => {
    if (!from || !to) {
      setData(null);
      setError('Chọn cả hai ngày.');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const r = await roomsApi.timetable(room.id, from, to);
      setData(r);
    } catch (e) {
      setData(null);
      setError(e instanceof ApiError ? e.message : 'Không tải được lịch phòng.');
    } finally {
      setLoading(false);
    }
  }, [room.id, from, to]);

  useEffect(() => {
    dialogRef.current?.showModal();
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Nhóm theo ngày — giữ thứ tự tăng dần.
  const byDay = useMemo(() => {
    const groups = new Map<string, RoomTimetable['items']>();
    for (const it of data?.items ?? []) {
      const k = dateOf(it.startsAt);
      const arr = groups.get(k) ?? [];
      arr.push(it);
      groups.set(k, arr);
    }
    return [...groups.entries()];
  }, [data]);

  const close = () => dialogRef.current?.close();

  return (
    <dialog
      ref={dialogRef}
      className="room-dlg"
      aria-labelledby="room-tl-title"
      onClose={onClose}
    >
      <div className="room-dlg__bar">
        <h2 id="room-tl-title" className="room-dlg__title">
          Lịch phòng {room.code}
        </h2>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          onClick={close}
          aria-label="Đóng lịch phòng"
        >
          <Icon name="close" size={16} />
          <span className="sr-only">Đóng</span>
        </button>
      </div>

      <div className="room-dlg__body">
        <div className="room-tl__range">
          <div className="field">
            <label className="field__label" htmlFor="room-tl-from">
              Từ ngày
            </label>
            <input
              id="room-tl-from"
              type="date"
              className="field__input"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
          </div>
          <div className="field">
            <label className="field__label" htmlFor="room-tl-to">
              Đến ngày
            </label>
            <input
              id="room-tl-to"
              type="date"
              className="field__input"
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </div>
        </div>

        {error && (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        )}

        {loading ? (
          <p className="eyebrow">Đang tải…</p>
        ) : !error && byDay.length === 0 ? (
          <div className="empty">
            <span className="empty__icon">
              <Icon name="calendar" size={22} />
            </span>
            <p className="empty__title">Phòng trống trong khoảng này</p>
            <p>Chưa có buổi học hay ca thi nào trong phòng {room.code}.</p>
          </div>
        ) : (
          <div className="room-tl__list">
            {byDay.map(([day, items]) => (
              <section key={day} aria-label={day}>
                <p className="room-tl__day">
                  {weekdayOf(items[0].startsAt)}, {day}
                </p>
                {items.map((it) => (
                  <div key={it.id} className="room-tl__row">
                    <span className="room-tl__time mono">
                      {timeOf(it.startsAt)}–{timeOf(it.endsAt)}
                    </span>
                    <span className="room-tl__course">
                      {it.course.code} — {it.course.name}
                    </span>
                    <span className="room-tl__cls mono">{it.class.code}</span>
                    <span className={`tag ${it.entryKind === 'EXAM' ? 'tag--seal' : 'tag--muted'}`}>
                      {it.entryKind === 'EXAM' ? 'Thi' : 'Học'}
                    </span>
                  </div>
                ))}
              </section>
            ))}
          </div>
        )}
      </div>
    </dialog>
  );
}
