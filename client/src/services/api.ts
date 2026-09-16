import type { RoleCode } from '@/utils/roles';

export const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:4000/api';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code?: string,
    public readonly fieldErrors?: string[],
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface NestErrorBody {
  message?: string | string[] | { message?: string; code?: string };
  code?: string;
  statusCode?: number;
}

/** Chuẩn hóa mọi hình dạng lỗi mà NestJS có thể trả về thành một `ApiError`. */
async function toApiError(res: Response): Promise<ApiError> {
  let body: NestErrorBody | null = null;
  try {
    body = (await res.json()) as NestErrorBody;
  } catch {
    return new ApiError(res.status, `Máy chủ trả về lỗi ${res.status}`);
  }

  // ValidationPipe trả `message` là mảng chuỗi, mỗi chuỗi một lỗi trường.
  if (Array.isArray(body?.message)) {
    return new ApiError(res.status, body.message[0] ?? 'Dữ liệu không hợp lệ', body.code, body.message);
  }
  // Các exception tự viết trả object { message, code }.
  if (body?.message && typeof body.message === 'object') {
    const m = body.message as { message?: string; code?: string };
    return new ApiError(res.status, m.message ?? 'Đã xảy ra lỗi', m.code);
  }
  return new ApiError(res.status, (body?.message as string) ?? 'Đã xảy ra lỗi', body?.code);
}

/**
 * Đang có một lần refresh chạy dở.
 *
 * Khi một trang bắn ba request song song và cả ba cùng gặp 401, ba lần gọi
 * `/auth/refresh` đồng thời sẽ khiến hai lần sau dùng phải token đã bị xoay —
 * mà backend coi đó là dấu hiệu token bị đánh cắp và thu hồi sạch phiên. Chia
 * chung một promise là cách duy nhất tránh việc tự đá mình ra ngoài.
 */
let refreshInFlight: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_URL}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  /** Nội bộ: chặn vòng lặp refresh vô hạn. */
  _retried?: boolean;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, _retried, headers, ...rest } = options;

  const res = await fetch(`${API_URL}${path}`, {
    ...rest,
    // Bắt buộc: token nằm trong cookie httpOnly, không nằm trong header.
    credentials: 'include',
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });

  if (res.status === 401 && !_retried) {
    const ok = await refreshSession();
    if (ok) return api<T>(path, { ...options, _retried: true });
  }

  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ------------------------------------------------------------------ kiểu dữ liệu

export interface StudyClassRef {
  id: string;
  code: string;
  name: string;
  faculty?: string | null;
}

export interface MeResponse {
  id: string;
  email: string;
  fullName: string;
  phone: string | null;
  status: 'ACTIVE' | 'SUSPENDED' | 'DISABLED';
  lastLoginAt: string | null;
  createdAt: string;
  roles: RoleCode[];
  roleNames: string[];
  hasSignaturePin: boolean;
  hasSignature?: boolean;
  studentProfile: {
    studentCode: string;
    dateOfBirth: string | null;
    placeOfBirth: string | null;
    gender: string | null;
    address: string | null;
    cohort: string | null;
    trainingSystem: string | null;
    enrollYear: number | null;
    studyClass: StudyClassRef | null;
  } | null;
}

export interface LoginResponse {
  user: {
    id: string;
    email: string;
    fullName: string;
    roles: RoleCode[];
    mustSetSignaturePin: boolean;
  };
  accessToken: string;
  expiresIn: number;
}

export const authApi = {
  login: (email: string, password: string) =>
    api<LoginResponse>('/auth/login', { method: 'POST', body: { email, password } }),
  logout: () => api<{ message: string }>('/auth/logout', { method: 'POST' }),
  me: () => api<MeResponse>('/users/me'),
  updateProfile: (data: { phone?: string; address?: string; placeOfBirth?: string }) =>
    api<MeResponse>('/users/me', { method: 'PATCH', body: data }),
  changePassword: (currentPassword: string, newPassword: string) =>
    api<{ message: string }>('/auth/change-password', {
      method: 'POST',
      body: { currentPassword, newPassword },
    }),
  setSignaturePin: (password: string, pin: string) =>
    api<{ message: string }>('/auth/signature-pin', { method: 'POST', body: { password, pin } }),
};
