import { STEP_STATUS_LABEL, STEP_STATUS_TAG, type StepStatus } from '@/services/approvals-api';
import { viDateTime, type SubmissionStatus } from '@/services/forms-api';
import { ROLE_LABEL, type RoleCode } from '@/utils/roles';

/**
 * Dải các cấp duyệt.
 *
 * Trước đây các bước được xếp dọc thành danh sách, mỗi bước một dòng có nẹp
 * trái. Đọc được, nhưng nó trả lời sai câu hỏi. Câu người dùng thực sự hỏi khi
 * mở một tờ đơn là *đơn của tôi đang nằm ở đâu* — một câu hỏi về **vị trí trên
 * chặng đường**, thứ mà dải ngang trả lời trong một cái liếc còn danh sách dọc
 * bắt đọc từng dòng rồi tự dựng lại.
 *
 * Ô số mang trạng thái chứ không phải là số thứ tự trang trí:
 *
 *   viền mảnh  — chưa tới
 *   viền đậm   — đang ở đây
 *   tô xanh    — đã xong
 *   tô đỏ      — đã từ chối hoặc trả lại
 *
 * Màu lặp lại nội dung của nhãn chữ bên cạnh, và đó là chủ ý: người không phân
 * biệt được màu vẫn đọc được nhãn, người liếc nhanh vẫn thấy được màu. Không
 * kênh nào là kênh duy nhất.
 */

export interface FlowStep {
  order: number;
  title: string;
  roleCode: string;
  /**
   * Trạng thái thật của bước, nếu bên gọi có.
   *
   * Hai trang dùng component này có hai lượng thông tin khác nhau, và đó là
   * thực tế của API chứ không phải thiếu sót: hộp thư cán bộ đọc bảng
   * `approval_steps` nên biết từng bước đã quyết ra sao; trang của học viên chỉ
   * có định nghĩa luồng trong biểu mẫu cộng với bước hiện hành.
   *
   * Bỏ trống thì trạng thái được **suy ra**, và suy ra thì phải suy cho đúng —
   * xem `derive()`.
   */
  status?: StepStatus;
  decidedAt?: string | null;
  comment?: string | null;
}

const DONE: StepStatus[] = ['APPROVED', 'SKIPPED'];
const BAD: StepStatus[] = ['REJECTED', 'REVISION_REQUESTED'];

/**
 * Suy trạng thái một bước khi chỉ biết bước hiện hành.
 *
 * Chỗ dễ sai: đơn bị **từ chối** hoặc bị **trả lại** thì bước hiện hành không
 * phải "đang chờ" mà là "đã có quyết định xấu". Suy nó thành "đang chờ" sẽ vẽ ra
 * một tờ đơn đang trôi bình thường trong khi thực tế nó đã dừng — đúng loại sai
 * khiến người nộp ngồi đợi một việc không bao giờ tới.
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
