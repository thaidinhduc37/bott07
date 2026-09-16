import { api, API_URL } from './api';
import type { FormField, SubmissionStatus } from './forms-api';

export type ApprovalActionType =
  | 'SUBMIT'
  | 'RESUBMIT'
  | 'RECEIVE'
  | 'APPROVE'
  | 'REJECT'
  | 'REQUEST_REVISION'
  | 'SIGN'
  | 'COMPLETE';

export type StepStatus =
  | 'PENDING'
  | 'IN_PROGRESS'
  | 'APPROVED'
  | 'REJECTED'
  | 'REVISION_REQUESTED'
  | 'SKIPPED';

export const ACTION_LABEL: Record<ApprovalActionType, string> = {
  SUBMIT: 'Gửi trình ký',
  RESUBMIT: 'Gửi lại sau khi bổ sung',
  RECEIVE: 'Tiếp nhận',
  APPROVE: 'Phê duyệt',
  REJECT: 'Từ chối',
  REQUEST_REVISION: 'Yêu cầu bổ sung',
  SIGN: 'Ký',
  COMPLETE: 'Hoàn thành',
};

export const STEP_STATUS_LABEL: Record<StepStatus, string> = {
  PENDING: 'Chờ tiếp nhận',
  IN_PROGRESS: 'Đang xem xét',
  APPROVED: 'Đã duyệt',
  REJECTED: 'Đã từ chối',
  REVISION_REQUESTED: 'Đã yêu cầu bổ sung',
  SKIPPED: 'Bỏ qua',
};

export const STEP_STATUS_TAG: Record<StepStatus, string> = {
  PENDING: 'tag--muted',
  IN_PROGRESS: 'tag--warn',
  APPROVED: 'tag--ok',
  REJECTED: 'tag--seal',
  REVISION_REQUESTED: 'tag--warn',
  SKIPPED: 'tag--muted',
};

export interface InboxStep {
  stepOrder: number;
  title: string;
  roleCode: string;
  status: StepStatus;
  decidedAt: string | null;
  comment: string | null;
}

export interface InboxItem {
  id: string;
  code: string;
  status: SubmissionStatus;
  statusLabel: string;
  submittedAt: string | null;
  currentStepOrder: number | null;
  owner: { id: string; fullName: string };
  studentCode: string | null;
  template: { code: string; name: string };
  steps: InboxStep[];
  currentStep: InboxStep | null;
}

export interface HistoryEntry {
  action: ApprovalActionType;
  actionLabel: string;
  actor: string;
  stepOrder: number | null;
  fromStatus: SubmissionStatus | null;
  toStatus: SubmissionStatus;
  comment: string | null;
  ipAddress: string | null;
  createdAt: string;
}

export interface ApprovalDetail {
  id: string;
  code: string;
  status: SubmissionStatus;
  statusLabel: string;
  currentStepOrder: number | null;
  createdAt: string;
  submittedAt: string | null;
  completedAt: string | null;
  signedHash: string | null;
  hasFile: boolean;
  owner: {
    fullName: string;
    email: string;
    studentCode: string | null;
    className: string | null;
  };
  template: { code: string; name: string };
  fields: FormField[];
  formData: Record<string, string>;
  profileSnapshot: Record<string, string>;
  steps: Array<InboxStep & { canAct: boolean }>;
  history: HistoryEntry[];
  signings: Array<{
    stepOrder: number | null;
    signedAt: string;
    hashBefore: string;
    hashAfter: string;
  }>;
}

export const approvalsApi = {
  inbox: (done = false) =>
    api<{ items: InboxItem[] }>(`/approvals${done ? '?daXuLy=1' : ''}`),

  detail: (id: string) => api<ApprovalDetail>(`/approvals/${id}`),

  act: (id: string, action: ApprovalActionType, opts: { comment?: string; pin?: string } = {}) =>
    api<ApprovalDetail>(`/approvals/${id}/action`, {
      method: 'POST',
      body: { action, ...opts },
    }),

  fileUrl: (id: string) => `${API_URL}/approvals/${id}/file`,
};

// ------------------------------------------------------------------ thông báo

export interface NotificationItem {
  id: string;
  type: string;
  title: string;
  body: string;
  linkTo: string | null;
  readAt: string | null;
  createdAt: string;
}

export const notificationsApi = {
  list: () => api<{ items: NotificationItem[]; unread: number }>('/notifications'),

  markRead: (ids?: string[]) =>
    api<{ marked: number }>('/notifications/read', { method: 'PATCH', body: { ids } }),
};
