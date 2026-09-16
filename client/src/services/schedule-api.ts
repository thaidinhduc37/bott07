import { API_URL, api } from './api';

export interface CourseRef {
  id: string;
  code: string;
  name: string;
  credits: number;
}

export interface Session {
  id: string;
  externalId: string | null;
  sessionDate: string;
  weekNumber: number | null;
  startPeriod: number;
  endPeriod: number;
  startsAt: string;
  endsAt: string;
  room: string;
  building: string | null;
  instructor: string | null;
  deliveryMode: string | null;
  sessionType: string;
  sessionTypeLabel: string;
  status: string;
  statusLabel: string;
  note: string | null;
  course: CourseRef;
  kind: 'SESSION';
}

export interface Exam {
  id: string;
  externalId: string | null;
  examDate: string;
  shift: string | null;
  startsAt: string;
  endsAt: string;
  durationMinutes: number;
  room: string;
  building: string | null;
  examFormat: string;
  formatLabel: string;
  allowedMaterials: string | null;
  chiefProctor: string | null;
  secondProctor: string | null;
  status: string;
  note: string | null;
  course: CourseRef;
  kind: 'EXAM';
}

export interface Timetable {
  class: { id: string; code: string; name: string } | null;
  range: { from: string; to: string; timezone: string };
  sessions: Session[];
  exams: Exam[];
}

export interface ImportError {
  line: number;
  column?: string;
  message: string;
}

export interface ImportConflict {
  a: string;
  b: string;
  kind: 'CLASS' | 'ROOM' | 'INSTRUCTOR';
  message: string;
}

export interface ImportResult {
  fileName: string;
  class: string;
  kind?: 'exam';
  totalRows: number;
  validRows: number;
  errors: ImportError[];
  conflicts: ImportConflict[];
  dryRun: boolean;
  accepted: boolean;
  imported: number;
  created?: number;
  updated?: number;
  newCourses?: string[];
  message: string;
}

export const scheduleApi = {
  mine: (params: { from?: string; to?: string; courseId?: string } = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v) as [string, string][],
    ).toString();
    return api<Timetable>(`/schedules/me${qs ? `?${qs}` : ''}`);
  },

  myCourses: () => api<{ items: CourseRef[] }>('/schedules/me/courses'),

  /**
   * Nạp CSV. `dryRun` chạy hết mọi kiểm tra nhưng không ghi gì — cán bộ cần biết
   * file sạch hay không TRƯỚC khi nó vào hệ thống.
   */
  import: async (file: File, classId: string, opts: { dryRun?: boolean; allowPartial?: boolean } = {}) => {
    const form = new FormData();
    form.append('file', file);
    form.append('classId', classId);
    if (opts.dryRun) form.append('dryRun', 'true');
    if (opts.allowPartial) form.append('allowPartial', 'true');

    // Không đặt Content-Type: trình duyệt phải tự sinh boundary của multipart.
    const res = await fetch(`${API_URL}/schedules/import`, {
      method: 'POST',
      credentials: 'include',
      body: form,
    });
    const body = await res.json();
    if (!res.ok) {
      throw Object.assign(new Error(body?.message ?? 'Nạp tệp thất bại'), { status: res.status, body });
    }
    return body as ImportResult;
  },
};

// ---------------------------------------------------------------- định dạng

const VN = 'Asia/Ho_Chi_Minh';

export function timeOf(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: VN,
  }).format(new Date(iso));
}

export function dateOf(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    timeZone: VN,
  }).format(new Date(iso));
}

export function weekdayOf(iso: string): string {
  const d = new Intl.DateTimeFormat('vi-VN', { weekday: 'long', timeZone: VN }).format(new Date(iso));
  // Intl trả "Thứ Hai"/"Chủ Nhật"; viết hoa chữ đầu cho nhất quán.
  return d.charAt(0).toUpperCase() + d.slice(1);
}

/** Khóa nhóm theo ngày, tính theo giờ Việt Nam chứ không theo giờ máy. */
export function dayKey(iso: string): string {
  return new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: VN,
  }).format(new Date(iso));
}

export function isoDate(d: Date): string {
  return new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: VN,
  }).format(d);
}

/** Thứ Hai của tuần chứa `d`, theo giờ Việt Nam. */
export function mondayOf(d: Date): Date {
  const vn = new Date(d.toLocaleString('en-US', { timeZone: VN }));
  const offset = (vn.getDay() + 6) % 7;
  vn.setDate(vn.getDate() - offset);
  vn.setHours(0, 0, 0, 0);
  return vn;
}
