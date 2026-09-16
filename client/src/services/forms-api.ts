import { api, API_URL } from './api';

export type SubmissionStatus =
  | 'DRAFT'
  | 'SUBMITTED'
  | 'UNDER_REVIEW'
  | 'NEEDS_REVISION'
  | 'REJECTED'
  | 'APPROVED'
  | 'COMPLETED';

export interface FormField {
  key: string;
  label: string;
  type: 'text' | 'date' | 'textarea' | 'course' | 'number' | 'table';
  required: boolean;
  /** Có mặt = giá trị đến từ hồ sơ; giao diện hiển thị khóa, không cho sửa. */
  autofill?: string;
  maxLength?: number;
  /** Chỉ `type: 'table'` — các cột người dùng nhập cho mỗi dòng. */
  columns?: Array<{ key: string; label: string; maxLength?: number }>;
  /** Chỉ `type: 'table'` — trần số dòng. */
  maxRows?: number;
}

/** Một dòng của trường dạng bảng. */
export type TableRowValue = Record<string, string>;

/**
 * Giá trị của một trường: chuỗi cho trường thường, mảng dòng cho trường bảng.
 */
export type FieldValue = string | TableRowValue[];

export interface ApprovalStepDef {
  order: number;
  roleCode: string;
  title: string;
}

export interface TemplateRef {
  id: string;
  code: string;
  name: string;
  description: string | null;
  isActive: boolean;
}

export interface TemplateDetail {
  id: string;
  code: string;
  name: string;
  description: string | null;
  fields: FormField[];
  autofill: Record<string, string>;
  missingProfileFields: Array<{ key: string; label: string }>;
  approvalFlow: ApprovalStepDef[];
}

export interface SubmissionSummary {
  id: string;
  code: string;
  status: SubmissionStatus;
  statusLabel: string;
  createdAt: string;
  submittedAt: string | null;
  generatedAt: string | null;
  signed: boolean;
  currentStepOrder: number | null;
  template: { code: string; name: string };
}

export interface SubmissionDetail {
  id: string;
  code: string;
  status: SubmissionStatus;
  statusLabel: string;
  editable: boolean;
  formData: Record<string, FieldValue>;
  profileSnapshot: Record<string, string>;
  generatedAt: string | null;
  generatedHash: string | null;
  signedHash: string | null;
  submittedAt: string | null;
  completedAt: string | null;
  currentStepOrder: number | null;
  createdAt: string;
  template: {
    code: string;
    name: string;
    fields: FormField[];
    approvalFlow: ApprovalStepDef[];
  };
}

export const STATUS_TAG: Record<SubmissionStatus, string> = {
  DRAFT: 'tag--muted',
  SUBMITTED: 'tag--pen',
  UNDER_REVIEW: 'tag--warn',
  NEEDS_REVISION: 'tag--warn',
  REJECTED: 'tag--seal',
  APPROVED: 'tag--ok',
  COMPLETED: 'tag--ok',
};

export const formsApi = {
  templates: () => api<{ items: TemplateRef[] }>('/form-templates'),
  template: (code: string) => api<TemplateDetail>(`/form-templates/${code}`),

  list: () => api<{ items: SubmissionSummary[]; total: number }>('/submissions'),
  get: (id: string) => api<SubmissionDetail>(`/submissions/${id}`),

  create: (templateCode: string, formData: Record<string, FieldValue>) =>
    api<SubmissionDetail>('/submissions', { method: 'POST', body: { templateCode, formData } }),

  update: (id: string, formData: Record<string, FieldValue>) =>
    api<SubmissionDetail>(`/submissions/${id}`, { method: 'PATCH', body: { formData } }),

  render: (id: string) =>
    api<{ code: string; hash: string; bytes: number; generatedAt: string }>(
      `/submissions/${id}/render`,
      { method: 'POST' },
    ),

  sign: (id: string, pin: string) =>
    api<SubmissionDetail>(`/submissions/${id}/sign`, { method: 'POST', body: { pin } }),

  submit: (id: string) =>
    api<SubmissionDetail>(`/submissions/${id}/submit`, { method: 'POST' }),

  verify: (id: string) => api<VerifyResult>(`/submissions/${id}/verify`),

  /** Chỉ xóa được đơn nháp chưa ký — backend tự chặn các trường hợp khác. */
  remove: (id: string) => api<{ message: string }>(`/submissions/${id}`, { method: 'DELETE' }),

  /** Đường dẫn tải file. Cookie đi kèm nên không cần token trên URL. */
  fileUrl: (id: string, variant: 'signed' | 'unsigned' = 'signed') =>
    `${API_URL}/submissions/${id}/file${variant === 'unsigned' ? '?ban=chua-ky' : ''}`,
};

export interface SigningRecord {
  signedAt: string;
  hashBefore: string;
  hashAfter: string;
  ipAddress: string | null;
  sessionId: string | null;
  stepOrder: number | null;
}

export type VerifyResult =
  | { signed: false; message: string }
  | {
      signed: true;
      matches: boolean;
      expectedHash: string;
      currentHash: string | null;
      readError: string | null;
      message: string;
      signings: SigningRecord[];
    };

export interface SignatureInfo {
  id: string;
  fileHash: string;
  widthPx: number | null;
  heightPx: number | null;
  createdAt: string;
}

export const signaturesApi = {
  mine: () => api<SignatureInfo | null>('/signatures/me'),

  imageUrl: () => `${API_URL}/signatures/me/image`,

  register: async (png: Blob) => {
    const form = new FormData();
    form.append('file', png, 'chu-ky.png');
    const res = await fetch(`${API_URL}/signatures`, {
      method: 'POST',
      credentials: 'include',
      body: form,
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      const m = body?.message;
      throw new Error(
        (typeof m === 'object' ? m?.message : Array.isArray(m) ? m[0] : m) ??
          'Không lưu được chữ ký',
      );
    }
    return body as SignatureInfo;
  },
};

export function viDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(new Date(iso));
}

export function viDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(new Date(iso));
}
