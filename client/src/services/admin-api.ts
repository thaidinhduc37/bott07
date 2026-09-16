import { api } from './api';
import type { RoleCode } from '@/utils/roles';
import type { SubmissionStatus } from './forms-api';

export type UserStatus = 'ACTIVE' | 'SUSPENDED' | 'DISABLED';

export const USER_STATUS_LABEL: Record<UserStatus, string> = {
  ACTIVE: 'Đang hoạt động',
  SUSPENDED: 'Tạm khóa',
  DISABLED: 'Đã vô hiệu hóa',
};

export const USER_STATUS_TAG: Record<UserStatus, string> = {
  ACTIVE: 'tag--ok',
  SUSPENDED: 'tag--warn',
  DISABLED: 'tag--seal',
};

export interface AdminUser {
  id: string;
  email: string;
  fullName: string;
  phone: string | null;
  status: UserStatus;
  lastLoginAt: string | null;
  createdAt: string;
  roles: RoleCode[];
  roleNames?: string[];
  studentProfile?: { studentCode: string; studyClass: { code: string } | null } | null;
}

export interface AuditLogEntry {
  id: string;
  action: string;
  entityType: string | null;
  entityId: string | null;
  detail: unknown;
  ipAddress: string | null;
  userAgent: string | null;
  createdAt: string;
  user: { id: string; email: string; fullName: string } | null;
}

export interface ServiceStatus {
  status: 'ok' | 'degraded';
  dependencies: {
    postgres: { ok: boolean; latencyMs: number | null };
    ragService: {
      ok: boolean;
      detail: string;
      url: string;
      collections: Record<
        string,
        { dense_points: number; sparse_documents: number; in_sync: boolean }
      >;
    };
    llm: { ok: boolean; detail?: string } | null;
  };
  counters: { users: number; indexedDocumentVersions: number; submissions: number };
  uptimeSeconds: number;
  memoryMb: number;
}

export const adminApi = {
  users: (params: { search?: string; role?: string; status?: string } = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v) as [string, string][],
    ).toString();
    return api<{ total: number; page: number; pageSize: number; items: AdminUser[] }>(
      `/admin/users${qs ? `?${qs}` : ''}`,
    );
  },

  setStatus: (id: string, status: UserStatus, reason?: string) =>
    api<AdminUser>(`/admin/users/${id}/status`, { method: 'PATCH', body: { status, reason } }),

  setRoles: (id: string, roles: RoleCode[]) =>
    api<AdminUser>(`/admin/users/${id}/roles`, { method: 'PUT', body: { roles } }),

  auditLogs: (params: { page?: number; action?: string; userId?: string } = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== '')
        .map(([k, v]) => [k, String(v)]),
    ).toString();
    return api<{ total: number; page: number; pageSize: number; items: AuditLogEntry[] }>(
      `/admin/audit-logs${qs ? `?${qs}` : ''}`,
    );
  },

  services: () => api<ServiceStatus>('/health/detail'),
};

// ------------------------------------------------------------ dashboard điều hành

export interface FormsAdminStats {
  byStatus: Array<{ status: SubmissionStatus; count: number }>;
  byTemplate: Array<{ templateName: string; count: number }>;
  avgTurnaroundDays: number | null;
  avgTurnaroundTrend: Array<{ day: string; value: number }>;
  backlog: Array<{
    code: string;
    templateName: string;
    status: SubmissionStatus;
    currentStepOrder: number | null;
    daysWaiting: number;
  }>;
  rejectionRate30d: number | null;
  rejectionRateTrend: Array<{ day: string; value: number }>;
}

export interface RagAdminStats {
  dailyTrend: Array<{
    day: string;
    total: number;
    abstained: number;
    avgConfidence: number | null;
    groundedFailures: number;
  }>;
  abstentionRate: number | null;
  groundedFailureRate: number | null;
  byMode: Array<{ mode: 'QUYCHE' | 'GIAOTRINH'; count: number }>;
  byRoute: Array<{ route: string; count: number }>;
}

export interface DocumentsAdminStats {
  byIndexStatus: Record<string, { versions: number; chunks: number }>;
  ragConsistency: string;
  byType: Array<{ documentType: 'QUYCHE' | 'GIAOTRINH' | 'KHAC'; count: number }>;
  failedList: Array<{ documentTitle: string; version: number; indexError: string | null; failedAt: string }>;
}

export interface ActivityAdminStats {
  activeUsers7d: number;
  activeUsers30d: number;
  usersByRole: Array<{ role: RoleCode; count: number }>;
  failedLogins7d: Array<{ day: string; count: number }>;
  scheduleThisWeek: number;
  examsNext14d: number;
}

export const adminDashboardApi = {
  forms: () => api<FormsAdminStats>('/admin/dashboard/forms'),
  rag: () => api<RagAdminStats>('/admin/dashboard/rag'),
  documents: () => api<DocumentsAdminStats>('/admin/dashboard/documents'),
  activity: () => api<ActivityAdminStats>('/admin/dashboard/activity'),
};
