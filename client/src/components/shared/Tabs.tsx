import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react';

export interface TabItem<T extends string> {
  id: T;
  label: string;
  /** Số nhỏ cạnh nhãn (vd số kỳ thi sắp tới). */
  badge?: number | string;
  /** Đọc cho trình đọc màn hình thay cho con số trần ("3 kỳ thi trong 14 ngày tới"). */
  badgeLabel?: string;
}

/**
 * Thanh tab dùng chung — mô hình WAI-ARIA "tabs": `role=tablist/tab`, chỉ tab đang chọn
 * nằm trong thứ tự Tab (roving tabindex), ← → Home End đổi tab và dời focus theo.
 *
 * Kiểu gạch chân, đặt SÁT ĐÁY `PageHeader` và ngay trên nội dung nó điều khiển. Dùng
 * `TabPanel` cùng `idPrefix` để nối `aria-controls` / `aria-labelledby` cho khớp.
 *
 * Chỉ dành cho việc ĐỔI PHẦN NỘI DUNG của trang. Bộ lọc (tất cả / chưa đọc…) hay điều
 * hướng tuần vẫn dùng nhóm `.seg`.
 */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
  idPrefix,
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (id: T) => void;
  /** Tên của cả nhóm tab cho trình đọc màn hình ("Nội dung trang Ôn tập"). */
  label: string;
  idPrefix?: string;
}) {
  const auto = useId();
  const prefix = idPrefix ?? auto;
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(e: KeyboardEvent) {
    const i = items.findIndex((t) => t.id === value);
    let next = -1;
    if (e.key === 'ArrowRight') next = (i + 1) % items.length;
    else if (e.key === 'ArrowLeft') next = (i - 1 + items.length) % items.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = items.length - 1;
    if (next === -1) return;
    e.preventDefault();
    const target = items[next].id;
    onChange(target);
    // Focus theo tab mới ngay: nút của tab đó đã có sẵn trong DOM.
    refs.current[target]?.focus();
  }

  return (
    <div className="tabs" role="tablist" aria-label={label} onKeyDown={onKeyDown}>
      {items.map((t) => {
        const selected = t.id === value;
        return (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el;
            }}
            type="button"
            role="tab"
            id={tabId(prefix, t.id)}
            className="tabs__tab"
            aria-selected={selected}
            aria-controls={panelId(prefix, t.id)}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(t.id)}
          >
            {t.label}
            {t.badge !== undefined && (
              <span className="tabs__badge" aria-label={t.badgeLabel}>
                {t.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

const tabId = (prefix: string, id: string) => `${prefix}-tab-${id}`;
const panelId = (prefix: string, id: string) => `${prefix}-panel-${id}`;

/** Vùng nội dung của một tab; `idPrefix` phải trùng với `Tabs`. */
export function TabPanel({
  idPrefix,
  tab,
  children,
}: {
  idPrefix: string;
  tab: string;
  children: ReactNode;
}) {
  return (
    <div role="tabpanel" id={panelId(idPrefix, tab)} aria-labelledby={tabId(idPrefix, tab)}>
      {children}
    </div>
  );
}
