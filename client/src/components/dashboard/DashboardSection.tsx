import type { ReactNode } from 'react';
import type { Loaded } from './useDashboardSection';

/** Khung dùng chung cho bốn khối dashboard: tiêu đề, mô tả, và ba trạng thái
 *  tải/lỗi/xong — mỗi khối tự quản lý trạng thái của riêng nó. */
export function DashboardSection<T>({
  title,
  desc,
  state,
  children,
}: {
  title: string;
  desc: string;
  state: Loaded<T>;
  children: (data: T) => ReactNode;
}) {
  return (
    <section className="sheet sheet--pad">
      <header className="dash-section__head">
        <h2 className="dash-section__title">{title}</h2>
        <p className="dash-section__desc">{desc}</p>
      </header>
      {state.status === 'loading' && <p className="eyebrow">Đang tải…</p>}
      {state.status === 'error' && (
        <div className="notice notice--error" role="alert">
          {state.message}
        </div>
      )}
      {state.status === 'ok' && <div className="stack">{children(state.data)}</div>}
    </section>
  );
}
