import { api, API_URL } from './api';

export type DocumentType = 'QUYCHE' | 'GIAOTRINH' | 'KHAC';
export type IndexStatus = 'UPLOADED' | 'PROCESSING' | 'INDEXED' | 'FAILED';

export const DOCUMENT_TYPE_LABEL: Record<DocumentType, string> = {
  QUYCHE: 'Quy chế, quy định',
  GIAOTRINH: 'Giáo trình, đề cương',
  KHAC: 'Tài liệu giảng dạy',
};

export const INDEX_STATUS_LABEL: Record<IndexStatus, string> = {
  UPLOADED: 'Chờ lập chỉ mục',
  PROCESSING: 'Đang lập chỉ mục',
  INDEXED: 'Đã lập chỉ mục',
  FAILED: 'Lập chỉ mục thất bại',
};

/** Chỉ hai loại này đi vào chỉ mục tìm kiếm — khớp với `INDEXABLE` ở API. */
export const INDEXABLE: DocumentType[] = ['QUYCHE', 'GIAOTRINH'];

export interface CourseRef {
  id: string;
  code: string;
  name: string;
  credits?: number;
}

export interface DocumentVersion {
  id: string;
  version: number;
  fileName: string;
  fileSize: number;
  mimeType: string;
  indexStatus: IndexStatus;
  indexError: string | null;
  indexedAt: string | null;
  pageCount: number | null;
  chunkCount: number | null;
  contextualCount: number | null;
}

export interface DocumentItem {
  id: string;
  title: string;
  documentType: DocumentType;
  referenceNo: string | null;
  issuedAt: string | null;
  createdAt: string;
  course: CourseRef | null;
  uploadedBy: { id: string; fullName: string };
  latestVersion: DocumentVersion | null;
}

export interface DocumentList {
  total: number;
  page: number;
  pageSize: number;
  items: DocumentItem[];
}

export interface CollectionHealth {
  dense_points: number;
  sparse_documents: number;
  in_sync: boolean;
}

export interface IndexStatusReport {
  postgres: Partial<Record<IndexStatus, { versions: number; chunks: number }>>;
  ragService:
    | { reachable: false }
    | {
        reachable: true;
        collections: Record<string, CollectionHealth>;
        llm: { ok: boolean; detail?: string; provider?: string };
      };
  /** `in_sync`, `unknown`, hoặc câu mô tả chỗ lệch — hiển thị nguyên văn. */
  consistency: string;
}

export interface UploadFields {
  title: string;
  documentType: DocumentType;
  courseId?: string;
  referenceNo?: string;
  issuedAt?: string;
}

export const documentsApi = {
  list: (params: { documentType?: string; search?: string; page?: number } = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== '')
        .map(([k, v]) => [k, String(v)]),
    ).toString();
    return api<DocumentList>(`/documents${qs ? `?${qs}` : ''}`);
  },

  indexStatus: () => api<IndexStatusReport>('/documents/index-status'),

  reindex: (id: string) =>
    api<{ message: string; status: IndexStatus }>(`/documents/${id}/reindex`, { method: 'POST' }),

  remove: (id: string) =>
    api<{ message: string; vectorsRemoved: number; filesRemoved: number }>(`/documents/${id}`, {
      method: 'DELETE',
    }),

  courses: () => api<{ items: CourseRef[] }>('/courses'),

  /**
   * Tải tệp lên. Không dùng `api()` vì đây là multipart: trình duyệt phải tự
   * sinh boundary, đặt Content-Type bằng tay sẽ hỏng request.
   */
  upload: async (file: File, fields: UploadFields) => {
    const form = new FormData();
    form.append('file', file);
    for (const [k, v] of Object.entries(fields)) {
      if (v) form.append(k, v);
    }
    const res = await fetch(`${API_URL}/documents`, {
      method: 'POST',
      credentials: 'include',
      body: form,
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      const message =
        typeof body?.message === 'object'
          ? body.message.message
          : Array.isArray(body?.message)
            ? body.message[0]
            : body?.message;
      throw Object.assign(new Error(message ?? 'Tải tệp lên thất bại'), {
        status: res.status,
        code: body?.message?.code ?? body?.code,
        body,
      });
    }
    return body as DocumentItem;
  },
};

// ---------------------------------------------------------------- định dạng

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(new Date(iso));
}
