/** Phân trang phía client cho danh sách vài trăm dòng ở các tab Quản lý đào tạo. */
export const PAGE_SIZE = 25;

export function Pager({
  page,
  total,
  onPage,
  pageSize = PAGE_SIZE,
}: {
  page: number;
  total: number;
  onPage: (p: number) => void;
  pageSize?: number;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <nav className="row train-pager" aria-label="Phân trang">
      <button type="button" className="btn btn--quiet" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Trang trước
      </button>
      <span className="field__hint">
        {from}–{to} / {total} · trang {page}/{pages}
      </span>
      <button type="button" className="btn btn--quiet" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Trang sau
      </button>
    </nav>
  );
}
