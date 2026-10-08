import { STEP_STATUS_LABEL, STEP_STATUS_TAG, type StepStatus } from '@/services/approvals-api';
import { viDateTime, type SubmissionStatus } from '@/services/forms-api';
import { ROLE_LABEL, type RoleCode } from '@/utils/roles';

/**
 * Dải các cấp duyệt: trả lời "đơn của tôi đang nằm ở đâu" trong một cái liếc, thay cho danh sách dọc. Ô số mang trạng thái: viền
 * mảnh = chưa tới, viền đậm = đang ở đây, tô xanh = đã xong, tô đỏ = từ chối hoặc trả lại. Màu lặp lại nhãn chữ bên cạnh có chủ ý để
 * không kênh nào là kênh duy nhất.
 */

export interface FlowStep {
  order: number;
  title: string;
  roleCode: string;
  /**
     * Trạng thái thật của bước, nếu bên gọi có: hộp thư cán bộ đọc `approval_steps` nên biết từng bước đã quyết ra sao, trang học viên
     * chỉ có định nghĩa luồng và bước hiện hành. Bỏ trống thì trạng thái được suy ra (xem `derive()`).
     */
  status?: StepStatus;
  decidedAt?: string | null;
  comment?: string | null;
}

const DONE: StepStatus[] = ['APPROVED', 'SKIPPED'];
const BAD: StepStatus[] = ['REJECTED', 'REVISION_REQUESTED'];

/**
 * Suy trạng thái một bước khi chỉ biết bước hiện hành. Đơn bị từ chối hoặc trả lại thì bước hiện hành là "đã có quyết định xấu",
 * không phải "đang chờ" (nếu không người nộp ngồi đợi một việc không bao giờ tới).
 */
function derive(
  order: number,
  currentStepOrder: number | null,
  submissionStatus?: SubmissionStatus,
): StepStatus {
  if (currentStepOrder === null) {
    // Chưa gửi trình ký: mọi bước đều còn ở phía trước.
    return 'PENDING';
  }
  if (order < currentStepOrder) return 'APPROVED';
  if (order > currentStepOrder) return 'PENDING';

  if (submissionStatus === 'REJECTED') return 'REJECTED';
  if (submissionStatus === 'NEEDS_REVISION') return 'REVISION_REQUESTED';
  if (submissionStatus === 'UNDER_REVIEW') return 'IN_PROGRESS';
  return 'PENDING';
}

function classOf(status: StepStatus, isCurrent: boolean): string {
  if (BAD.includes(status)) return 'flow__step flow__step--rejected';
  if (DONE.includes(status)) return 'flow__step flow__step--done';
  if (isCurrent) return 'flow__step flow__step--current';
  return 'flow__step';
}

export function ApprovalFlow({
  steps,
  currentStepOrder,
  submissionStatus,
  variant = 'horizontal',
}: {
  steps: FlowStep[];
  currentStepOrder: number | null;
  submissionStatus?: SubmissionStatus;
  /** 'vertical' — timeline một cột, dùng khi đặt cạnh khung xem trước tài
   * liệu hẹp; mặc định vẫn là dải ngang gốc (đọc `variant`-`horizontal` phía
   * trên trong docstring của file để biết lý do chọn ngang làm mặc định). */
  variant?: 'horizontal' | 'vertical';
}) {
  if (steps.length === 0) return null;

  return (
    <div className={variant === 'vertical' ? 'flow flow--vertical' : 'flow'}>
      {steps.map((s) => {
        const status = s.status ?? derive(s.order, currentStepOrder, submissionStatus);
        const isCurrent = currentStepOrder !== null && s.order === currentStepOrder;

        return (
          <div key={s.order} className={classOf(status, isCurrent)}>
            <span className="flow__n" aria-hidden="true">
              {s.order}
            </span>
            <div style={{ minWidth: 0 }}>
              <div className="flow__role">{s.title}</div>
              <div className="flow__who">{ROLE_LABEL[s.roleCode as RoleCode] ?? s.roleCode}</div>
              <span
                className={`tag ${STEP_STATUS_TAG[status]}`}
                style={{ marginTop: 'var(--gap-2)' }}
              >
                {STEP_STATUS_LABEL[status]}
              </span>
              {s.decidedAt && (
                <div
                  className="mono"
                  style={{ fontSize: '0.6875rem', color: 'var(--ink-faint)', marginTop: '0.3rem' }}
                >
                  {viDateTime(s.decidedAt)}
                </div>
              )}
              {s.comment && (
                <p
                  style={{
                    margin: '0.4rem 0 0',
                    fontSize: '0.8125rem',
                    color: 'var(--ink-soft)',
                    lineHeight: 1.5,
                  }}
                >
                  “{s.comment}”
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
