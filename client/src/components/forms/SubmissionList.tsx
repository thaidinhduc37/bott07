import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { STATUS_TAG, formsApi, viDate, type SubmissionStatus, type SubmissionSummary } from '@/services/forms-api';

type Filter = 'all' | 'processing' | 'done' | 'draft' | 'rejected';

const GROUPS: { id: Exclude<Filter, 'all'>; label: string; statuses: SubmissionStatus[] }[] = [
  { id: 'processing', label: 'Đang xử lý', statuses: ['SUBMITTED', 'UNDER_REVIEW', 'NEEDS_REVISION'] },
  { id: 'done', label: 'Đã duyệt', statuses: ['APPROVED', 'COMPLETED'] },
  { id: 'draft', label: 'Bản nháp', statuses: ['DRAFT'] },
  { id: 'rejected', label: 'Từ chối', statuses: ['REJECTED'] },
];

/** Chuẩn hóa để lọc không phân biệt hoa thường và dấu. */
const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').toLowerCase();

/**
 * Danh sách đơn của học viên: chip lọc theo nhóm trạng thái (kèm số đếm), ô lọc theo tên hoặc mã,
 * mỗi hàng có nhãn trạng thái, bước đang chờ và nút "Chi tiết" / "Tải bản đã ký" khi đơn đã ký.
 */
export function SubmissionList({ items }: { items: SubmissionSummary[] }) {
  const [filter, setFilter] = useState<Filter>('all');
  const [q, setQ] = useState('');

  const counts = useMemo(
    () =>
      Object.fromEntries(
        GROUPS.map((g) => [g.id, items.filter((s) => g.statuses.includes(s.status)).length]),
      ) as Record<Exclude<Filter, 'all'>, number>,
    [items],
  );

  const visible = useMemo(() => {
    const group = GROUPS.find((g) => g.id === filter);
    const needle = fold(q.trim());
    return items.filter(
      (s) =>
        (!group || group.statuses.includes(s.status)) &&
        (!needle || fold(`${s.code} ${s.template.name}`).includes(needle)),
    );
  }, [items, filter, q]);

  if (items.length === 0) {
    return (
      <div className="sheet sheet--pad">
        <p style={{ margin: 0, color: 'var(--ink-soft)' }}>
          Bạn chưa lập đơn nào. Chọn một mẫu ở danh mục bên cạnh để bắt đầu.
        </p>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="sub-bar">
        <div className="sub-chips" role="group" aria-label="Lọc theo trạng thái">
          <button
            type="button"
            className={`sub-chip${filter === 'all' ? ' sub-chip--on' : ''}`}
            aria-pressed={filter === 'all'}
            onClick={() => setFilter('all')}
          >
            Tất cả <span className="sub-chip__n">{items.length}</span>
          </button>
          {GROUPS.filter((g) => counts[g.id] > 0).map((g) => (
            <button
              key={g.id}
              type="button"
              className={`sub-chip${filter === g.id ? ' sub-chip--on' : ''}`}
              aria-pressed={filter === g.id}
              onClick={() => setFilter(g.id)}
            >
              {g.label} <span className="sub-chip__n">{counts[g.id]}</span>
            </button>
          ))}
        </div>
        <input
          type="search"
          className="field__input sub-search"
          placeholder="Lọc theo tên hoặc mã đơn"
          aria-label="Lọc theo tên hoặc mã đơn"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      {visible.length === 0 ? (
        <div className="sheet sheet--pad">
          <p style={{ margin: 0, color: 'var(--ink-soft)' }}>Không có đơn nào khớp bộ lọc.</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Mã đơn</th>
                <th>Loại đơn</th>
                <th>Ngày lập</th>
                <th>Trạng thái</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {visible.map((s) => (
                <tr key={s.id}>
                  <td className="mono" style={{ whiteSpace: 'nowrap', color: 'var(--ink-soft)' }}>
                    {s.code}
                  </td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{s.template.name}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', marginTop: '0.15rem' }}>
                      {s.signed ? 'đã ký' : 'chưa ký'}
                      {s.submittedAt && ` · gửi ${viDate(s.submittedAt)}`}
                    </div>
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>{viDate(s.createdAt)}</td>
                  <td>
                    <span className={`tag ${STATUS_TAG[s.status]}`}>{s.statusLabel}</span>
                    {s.currentStepOrder !== null && PENDING.includes(s.status) && (
                      <div className="sub-step">Đang chờ cấp {s.currentStepOrder}</div>
                    )}
                  </td>
                  <td>
                    <div className="sub-actions">
                      {s.signed && s.status !== 'DRAFT' && (
                        <a
                          href={formsApi.fileUrl(s.id, 'signed')}
                          className="btn btn--quiet"
                          target="_blank"
                          rel="noreferrer"
                        >
                          Tải bản đã ký
                        </a>
                      )}
                      <Link to={`/sinh-vien/don-cua-toi/${s.id}`} className="btn btn--quiet">
                        Chi tiết
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** Đơn đang nằm ở một bước duyệt (có `currentStepOrder`). */
const PENDING: SubmissionStatus[] = ['SUBMITTED', 'UNDER_REVIEW'];
