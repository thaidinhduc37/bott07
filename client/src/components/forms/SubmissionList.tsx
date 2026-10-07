import { Metrics } from '@/components/shared/Metrics';
import { Link } from 'react-router-dom';
import { STATUS_TAG, viDate, type SubmissionStatus, type SubmissionSummary } from '@/services/forms-api';

const PROCESSING: SubmissionStatus[] = ['SUBMITTED', 'UNDER_REVIEW', 'NEEDS_REVISION'];
const DONE: SubmissionStatus[] = ['APPROVED', 'COMPLETED'];

export function SubmissionList({ items }: { items: SubmissionSummary[] }) {
  if (items.length === 0) {
    return (
      <div className="sheet sheet--pad">
        <p style={{ margin: 0, color: 'var(--ink-soft)' }}>
          Bạn chưa lập đơn nào. Bắt đầu từ nút "Tạo đơn mới" phía trên.
        </p>
      </div>
    );
  }

  const processing = items.filter((s) => PROCESSING.includes(s.status)).length;
  const done = items.filter((s) => DONE.includes(s.status)).length;
  const rejected = items.filter((s) => s.status === 'REJECTED').length;

  return (
    <div className="stack">
      <Metrics
        label="Thống kê đơn"
        items={[
          { label: 'Tổng số đơn', value: items.length },
          { label: 'Đang xử lý', value: processing },
          { label: 'Đã duyệt', value: done, tone: done > 0 ? 'ok' : undefined },
          { label: 'Không được duyệt', value: rejected, tone: rejected > 0 ? 'seal' : undefined },
        ]}
      />

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
            {items.map((s) => (
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
                </td>
                <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                  <Link to={`/sinh-vien/don-cua-toi/${s.id}`} className="btn btn--quiet">
                    Chi tiết
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
