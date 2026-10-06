import { API_URL, api } from './api';

/**
 * API nhập điểm cho giảng viên / phòng đào tạo. Tách riêng khỏi `grades-api.ts`
 * (phần dành cho học viên) để hai phía không phụ thuộc lẫn nhau.
 *
 * Hợp đồng backend (JSON camelCase), xem `server/app/routers/grades.py`:
 *  - `GET  /grades/sections`            → { items: GradeSection[] }
 *  - `GET  /grades/sections/roster?...` → Roster
 *  - `PUT  /grades/sections/scores`     → SaveScoresResult
 *  - `POST /grades/import?dryRun=...`   → ImportResult (multipart, chỉ quản lý)
 */

export interface GradeCourse {
  id: string;
  code: string;
  name: string;
  credits: number;
}

export interface GradeClass {
  id: string;
  code: string;
  name: string;
}

/** Một (môn, lớp, năm học, học kỳ) mà người gọi được nhập điểm. */
export interface GradeSection {
  course: GradeCourse;
  class: GradeClass;
  academicYear: string;
  semester: string;
  studentCount: number;
  gradedCount: number;
}

/** Một học viên trong danh sách nhập điểm. */
export interface RosterStudent {
  studentId: string;
  studentCode: string;
  fullName: string;
  practice: number | null;
  process: number | null;
  midterm: number | null;
  finalExam: number | null;
  total: number | null;
  note: string | null;
}

export interface Roster {
  course: GradeCourse;
  class: GradeClass;
  academicYear: string;
  semester: string;
  students: RosterStudent[];
}

/** Một dòng điểm cần lưu — chỉ gửi các trường đã sửa. */
export interface ScoreInput {
  studentId: string;
  practice?: number | null;
  process?: number | null;
  midterm?: number | null;
  finalExam?: number | null;
  total?: number | null;
  note?: string | null;
}

export interface SaveScoresResult {
  message: string;
  created: number;
  updated: number;
  unchanged: number;
  course: string;
}

export interface ImportError {
  line: number;
  message: string;
}

export interface ImportResult {
  fileName: string | null;
  totalRows: number;
  validRows: number;
  errors: ImportError[];
  dryRun: boolean;
  accepted: boolean;
  created: number;
  updated: number;
  unchanged: number;
  message: string;
}

export const gradesStaffApi = {
  /** Danh sách học phần (môn · lớp · học kỳ) người gọi được nhập điểm. */
  sections: () => api<{ items: GradeSection[] }>('/grades/sections'),

  /** Danh sách học viên + điểm hiện tại của một học phần. */
  roster: (params: { courseId: string; classId: string; academicYear: string; semester: string }) => {
    const qs = new URLSearchParams({
      courseId: params.courseId,
      classId: params.classId,
      academicYear: params.academicYear,
      semester: params.semester,
    }).toString();
    return api<Roster>(`/grades/sections/roster?${qs}`);
  },

  /** Lưu điểm — chỉ gồm các dòng đã sửa. */
  saveScores: (body: {
    courseId: string;
    academicYear: string;
    semester: string;
    items: ScoreInput[];
  }) => api<SaveScoresResult>('/grades/sections/scores', { method: 'PUT', body }),

  /**
   * Nhập điểm từ CSV. `dryRun` chạy hết kiểm tra nhưng không ghi gì.
   * Không đặt `Content-Type`: trình duyệt tự sinh boundary của multipart.
   */
  import: async (file: File, dryRun: boolean): Promise<ImportResult> => {
    const form = new FormData();
    form.append('file', file);
    const qs = new URLSearchParams();
    if (dryRun) qs.set('dryRun', 'true');

    const res = await fetch(`${API_URL}/grades/import?${qs.toString()}`, {
      method: 'POST',
      credentials: 'include',
      body: form,
    });
    const body = (await res.json().catch(() => null)) as
      | { message?: string; code?: string }
      | ImportResult
      | null;
    if (!res.ok) {
      const msg = body && 'message' in body && typeof body.message === 'string' ? body.message : 'Nạp tệp thất bại';
      throw Object.assign(new Error(msg), { status: res.status, body });
    }
    return body as ImportResult;
  },
};
