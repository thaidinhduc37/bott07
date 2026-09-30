import { API_URL, api } from './api';

export interface CourseRef {
  id: string;
  code: string;
  name: string;
  credits: number;
}

/** Giảng viên phụ trách MÔN (tài khoản trong hệ thống). Khác `instructor` của buổi
 *  học — tên người đứng lớp buổi đó lấy từ CSV (có thể là người dạy thay). */
export interface LecturerRef {
  id: string;
  name: string;
  email: string;
}

/** Yêu cầu/ghi chú của giảng viên cho riêng buổi học / ca thi này. */
export interface LecturerNote {
  text: string;
  updatedAt: string;
  updatedBy: string | null;
}

export interface ClassRef {
  id: string;
  code: string;
  name: string;
}

export interface Session {
  id: string;
  externalId: string | null;
  academicYear?: string;
  semester?: string;
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
  /** Ghi chú đi kèm tệp CSV của phòng đào tạo. */
  note: string | null;
  course: CourseRef;
  kind: 'SESSION';
  lecturer: LecturerRef | null;
  lecturerNote: LecturerNote | null;
  /** Chỉ có trong lịch giảng dạy (`/schedules/teaching`). */
  class?: ClassRef | null;
}

export interface Exam {
  id: string;
  externalId: string | null;
  academicYear?: string;
  semester?: string;
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
  candidateCount: number | null;
  course: CourseRef;
  kind: 'EXAM';
  lecturer: LecturerRef | null;
  lecturerNote: LecturerNote | null;
  class?: ClassRef | null;
}

export type ScheduleEntry = Session | Exam;

export interface TeachingTimetable {
  range: { from: string; to: string; timezone: string };
  /** Cán bộ quản lý / quản trị: ghi chú được mọi môn. Giảng viên: chỉ môn mình. */
  canEditAll: boolean;
  sessions: Session[];
  exams: Exam[];
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

/* ------------------------------------------------- kiểu cho tạo/sửa/xóa buổi & ca */

/** Một va chạm lịch mà backend trả về trong lỗi 409 `SCHEDULE_CONFLICT`. */
export interface Conflict {
  kind: 'CLASS' | 'ROOM' | 'LECTURER';
  entryKind: 'SESSION' | 'EXAM';
  id: string;
  course: { code: string; name: string };
  class: { code: string };
  room: string;
  startsAt: string;
  endsAt: string;
}

/** Phòng gợi ý khi hỏi `GET /schedules/availability`. */
export interface AvailabilityRoom {
  room: string;
  building: string | null;
  busy: boolean;
  by: Conflict | null;
  /** Từ danh mục phòng học (agent F) — `null` khi phòng chưa trong danh mục. */
  capacity: number | null;
  kind: string | null;
  /** `true` khi phòng đã có trong danh mục `/rooms`. */
  registered: boolean;
}

/** Giảng viên gợi ý khi hỏi `GET /schedules/availability`. */
export interface AvailabilityLecturer {
  id: string;
  fullName: string;
  busy: boolean;
  by: Conflict | null;
}

export interface Availability {
  date: string;
  rooms: AvailabilityRoom[];
  lecturers: AvailabilityLecturer[];
}

/** Môn kèm giảng viên phụ trách — trả về `GET /courses`. */
export interface CourseWithLecturer {
  id: string;
  code: string;
  name: string;
  credits: number;
  description: string | null;
  lecturer: { id: string; fullName: string } | null;
}

/** Dữ liệu tạo buổi học — mọi trường bắt buộc của `POST /schedules`. */
export interface CreateSessionInput {
  classId: string;
  courseId: string;
  academicYear: string;
  semester: string;
  sessionDate: string;
  weekNumber?: number | null;
  startPeriod: number;
  endPeriod: number;
  startTime: string;
  endTime: string;
  room: string;
  building?: string | null;
  instructor?: string | null;
  deliveryMode?: string | null;
  sessionType?: string;
  status?: string;
  note?: string | null;
}

/** Dữ liệu sửa buổi học — mọi trường tùy chọn của `PATCH /schedules/:id`. */
export interface UpdateSessionInput {
  courseId?: string;
  sessionDate?: string;
  weekNumber?: number | null;
  startPeriod?: number;
  endPeriod?: number;
  startTime?: string;
  endTime?: string;
  room?: string;
  building?: string | null;
  instructor?: string | null;
  deliveryMode?: string | null;
  sessionType?: string;
  status?: string;
  note?: string | null;
}

/** Dữ liệu tạo ca thi — mọi trường bắt buộc của `POST /schedules/exams`. */
export interface CreateExamInput {
  classId: string;
  courseId: string;
  academicYear: string;
  semester: string;
  examDate: string;
  startTime: string;
  durationMinutes: number;
  room: string;
  building?: string | null;
  examFormat?: string;
  allowedMaterials?: string | null;
  candidateCount?: number | null;
  chiefProctor?: string | null;
  secondProctor?: string | null;
  note?: string | null;
}

/** Dữ liệu sửa ca thi — mọi trường tùy chọn của `PATCH /schedules/exams/:id`. */
export interface UpdateExamInput {
  courseId?: string;
  examDate?: string;
  startTime?: string;
  durationMinutes?: number;
  room?: string;
  building?: string | null;
  examFormat?: string;
  allowedMaterials?: string | null;
  candidateCount?: number | null;
  chiefProctor?: string | null;
  secondProctor?: string | null;
  note?: string | null;
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

  /** Lịch giảng dạy: buổi học + ca thi người gọi được ghi yêu cầu. */
  teaching: (params: { from?: string; to?: string; classId?: string } = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v) as [string, string][],
    ).toString();
    return api<TeachingTimetable>(`/schedules/teaching${qs ? `?${qs}` : ''}`);
  },

  /** Ghi / xóa (note rỗng) yêu cầu của giảng viên. `notify=false` khi chỉ sửa chính tả. */
  setLecturerNote: (entry: Pick<ScheduleEntry, 'kind' | 'id'>, note: string | null, notify = true) =>
    api<ScheduleEntry>(
      `/schedules/${entry.kind === 'EXAM' ? 'exams' : 'sessions'}/${entry.id}/lecturer-note`,
      { method: 'PUT', body: { note, notify } },
    ),

  /** Danh sách môn kèm giảng viên phụ trách — cho form tạo/sửa buổi & ca thi. */
  courses: () => api<{ items: CourseWithLecturer[] }>('/courses'),

  /** Phòng + giảng viên rảnh trong khoảng giờ — cho gợi ý phòng và cảnh báo trùng. */
  availability: (params: {
    date: string;
    startTime: string;
    endTime: string;
    excludeId?: string;
  }) => {
    const qs = new URLSearchParams(params).toString();
    return api<Availability>(`/schedules/availability?${qs}`);
  },

  createSession: (input: CreateSessionInput) =>
    api<Session>('/schedules', { method: 'POST', body: input }),

  updateSession: (id: string, input: UpdateSessionInput) =>
    api<Session>(`/schedules/${id}`, { method: 'PATCH', body: input }),

  deleteSession: (id: string) => api<{ message: string }>(`/schedules/${id}`, { method: 'DELETE' }),

  createExam: (input: CreateExamInput) =>
    api<Exam>('/schedules/exams', { method: 'POST', body: input }),

  updateExam: (id: string, input: UpdateExamInput) =>
    api<Exam>(`/schedules/exams/${id}`, { method: 'PATCH', body: input }),

  deleteExam: (id: string) => api<{ message: string }>(`/schedules/exams/${id}`, { method: 'DELETE' }),

  /**
   * Nạp CSV. `dryRun` chạy hết mọi kiểm tra nhưng không ghi gì — cán bộ cần biết
   * file sạch hay không TRƯỚC khi nó vào hệ thống.
   */
  import: async (file: File, classId: string, opts: { dryRun?: boolean; allowPartial?: boolean } = {}) => {
    const form = new FormData();
    form.append('file', file);
    // classId / dryRun / allowPartial đi trên query string — backend đọc chúng
    // bằng `Query(...)`; gửi trong form thì bị bỏ qua và báo "classId: Field required".
    const qs = new URLSearchParams({ classId });
    if (opts.dryRun) qs.set('dryRun', 'true');
    if (opts.allowPartial) qs.set('allowPartial', 'true');

    // Không đặt Content-Type: trình duyệt phải tự sinh boundary của multipart.
    const res = await fetch(`${API_URL}/schedules/import?${qs}`, {
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
