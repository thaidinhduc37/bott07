import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { notificationsApi, type NotificationItem } from '@/services/approvals-api';
import { Icon, type IconName } from '@/components/shared/Icon';
import { viDateTime } from '@/services/forms-api';

const TYPE_ICON: Record<string, IconName> = {
  SUBMISSION_STATUS: 'form',
  SCHEDULE_CHANGE: 'calendar',
  DOCUMENT_INDEXED: 'folder',
  SYSTEM: 'bell',
};

type Filter = 'all' | 'unread';

/** "Hôm nay, 14:30" / "Hôm qua, 09:05" — dễ quét hơn ngày-giờ đầy đủ lặp lại
 *  trên mỗi dòng. Thông báo cũ hơn hôm qua vẫn hiện ngày đầy đủ. */
function relativeWhen(iso: string): string {
  const d = new Date(iso);
  const startOfDay = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diffDays = Math.round((startOfDay(new Date()) - startOfDay(d)) / 86_400_000);
  const time = d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', hour12: false });
  if (diffDays === 0) return `Hôm nay, ${time}`;
  if (diffDays === 1) return `Hôm qua, ${time}`;
  return viDateTime(iso);
}

export default function NotificationsPage() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('all');

  const load = useCallback(async () => {
    try {
      const r = await notificationsApi.list();
      setItems(r.items);
      setUnread(r.unread);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function markAll() {
    await notificationsApi.markRead();
    await load();
  }

  /** Đánh dấu lạc quan trước khi chờ API — bấm vào một thông báo rồi chuyển
   *  trang thì người dùng không thấy được kết quả gọi API nữa, nên phải cập
   *  nhật UI ngay tại chỗ. */
  async function markOne(id: string) {
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, readAt: new Date().toISOString() } : n)));
    setUnread((prev) => Math.max(0, prev - 1));
    await notificationsApi.markRead([id]);
  }

  const visible = useMemo(
    () => (filter === 'unread' ? items.filter((n) => !n.readAt) : items),
    [items, filter],
  );

  return (
    <div className="stack shell--read">
      <header className="spread" style={{ alignItems: 'flex-end', gap: 'var(--gap-4)' }}>
        <div>
          <span className="eyebrow">Hộp thư</span>
          <h1 className="display page-title">Thông báo</h1>
          <p className="page-sub">{unread > 0 ? `${unread} thông báo chưa đọc` : 'Bạn đã đọc hết'}</p>
        </div>
        {unread > 0 && (
          <button type="button" className="btn btn--ghost" style={{ flexShrink: 0 }} onClick={markAll}>
            Đánh dấu đã đọc tất cả
          </button>
        )}
      </header>

      <fieldset style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}>
        <legend className="sr-only">Lọc thông báo</legend>
        <div className="seg">
          {(
            [
              ['all', 'Tất cả'],
              ['unread', `Chưa đọc${unread > 0 ? ` (${unread})` : ''}`],
            ] as const
          ).map(([value, label]) => (
            <label key={value} className={`seg__opt${filter === value ? ' seg__opt--on' : ''}`}>
              <input type="radio" name="filter" checked={filter === value} onChange={() => setFilter(value)} />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <p className="eyebrow">Đang tải…</p>
      ) : visible.length === 0 ? (
        <div className="empty">
          <span className="empty__icon" aria-hidden="true">
            <Icon name="bell" size={22} />
          </span>
          <p className="empty__title">
            {filter === 'unread' ? 'Không có thông báo chưa đọc' : 'Chưa có thông báo nào'}
          </p>
        </div>
      ) : (
        <div className="sheet action-list">
          {visible.map((n) => {
            const isUnread = !n.readAt;
            const inner = (
              <>
                <span
                  className={`action-row__icon${isUnread ? '' : ' action-row__icon--read'}`}
                  aria-hidden="true"
                >
                  <Icon name={TYPE_ICON[n.type] ?? 'bell'} size={20} />
                </span>
                <span className="action-row__body">
                  <span className="action-row__title" style={{ fontWeight: isUnread ? 600 : 500 }}>
                    {n.title}
                  </span>
                  <span className="action-row__desc">{n.body}</span>
                  <span className="action-row__pending">
                    <span className="mono" style={{ fontSize: '0.6875rem', color: 'var(--ink-faint)' }}>
                      {relativeWhen(n.createdAt)}
                    </span>
                  </span>
                </span>
                {n.linkTo && (
                  <span className="action-row__go" aria-hidden="true">
                    <Icon name="arrow" size={18} />
                  </span>
                )}
              </>
            );

            if (n.linkTo) {
              return (
                <Link
                  key={n.id}
                  to={n.linkTo}
                  className="action-row"
                  onClick={() => {
                    if (isUnread) void markOne(n.id);
                  }}
                >
                  {inner}
                </Link>
              );
            }

            if (isUnread) {
              return (
                <button key={n.id} type="button" className="action-row" onClick={() => void markOne(n.id)}>
                  {inner}
                </button>
              );
            }

            return (
              <div key={n.id} className="action-row">
                {inner}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
