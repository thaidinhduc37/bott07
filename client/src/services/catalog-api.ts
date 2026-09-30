import { api } from './api';

/**
 * Catalog đào tạo: lớp, môn học, giảng viên, học viên.
 *
 * Hợp đồng backend (agent A) — JSON camelCase, prefix `/catalog`. Mọi thao tác
 * ghi đều được audit phía server; phía client chỉ gọi và tải lại danh sách.
 */

export interface ClassItem {
  id: string;
  code: string;
  name: string;
  faculty: string | null;
  facultyId: string | null;
  cohortYear: number | null;
  studentCount: number;
  sessionCount: number;
}

export interface CourseItem {
  id: string;
  code: string;
  name: string;
  credits: number;
  description: string | null;
  lecturer: { id: string; fullName: string; email: string } | null;
  facultyId: string | null;
  facultyName: string | null;
  sessionCount: number;
}

export interface LecturerItem {
  id: string;
  fullName: string;
  email: string;
  courseCount: number;
  facultyId: string | null;
  facultyName: string | null;
}

export interface StudentItem {
  id: string;
  studentCode: string;
  fullName: string;
  email: string;
  cohort: string | null;
  class: { id: string; code: string; name: string } | null;
}

/** Tham số lọc trang Học viên. Trống / undefined = không lọc. */
export interface StudentsQuery {
  classId?: string;
  search?: string;
  /** true = chỉ học viên chưa có lớp. */
  unassigned?: boolean;
  page?: number;
  pageSize?: number;
}

export interface StudentsResult {
  total: number;
  page: number;
  pageSize: number;
  items: StudentItem[];
}

/** Dữ liệu form lớp — dùng chung cho thêm và sửa. */
export interface ClassPayload {
  code: string;
  name: string;
  faculty?: string | null;
  facultyId?: string | null;
  cohortYear?: number | null;
}

/** Dữ liệu form môn học — dùng chung cho thêm và sửa. */
export interface CoursePayload {
  code: string;
  name: string;
  credits: number;
  description?: string | null;
  /** `null` = bỏ gán giảng viên (khi sửa). */
  lecturerId?: string | null;
  facultyId?: string | null;
}

export const catalogApi = {
  /* ---- Lớp ---- */
  classes: () => api<{ items: ClassItem[] }>('/catalog/classes'),
  createClass: (data: ClassPayload) =>
    api<ClassItem>('/catalog/classes', { method: 'POST', body: data }),
  updateClass: (id: string, data: Partial<ClassPayload>) =>
    api<ClassItem>(`/catalog/classes/${id}`, { method: 'PATCH', body: data }),
  deleteClass: (id: string) =>
    api<{ message: string }>(`/catalog/classes/${id}`, { method: 'DELETE' }),

  /* ---- Môn học ---- */
  courses: () => api<{ items: CourseItem[] }>('/catalog/courses'),
  createCourse: (data: CoursePayload) =>
    api<CourseItem>('/catalog/courses', { method: 'POST', body: data }),
  updateCourse: (id: string, data: Partial<CoursePayload>) =>
    api<CourseItem>(`/catalog/courses/${id}`, { method: 'PATCH', body: data }),
  deleteCourse: (id: string) =>
    api<{ message: string }>(`/catalog/courses/${id}`, { method: 'DELETE' }),

  /* ---- Giảng viên (danh sách để gán môn) ---- */
  lecturers: () => api<{ items: LecturerItem[] }>('/catalog/lecturers'),

  /* ---- Học viên ---- */
  students: (q: StudentsQuery = {}) => {
    const params = new URLSearchParams();
    if (q.classId) params.set('classId', q.classId);
    if (q.search) params.set('search', q.search);
    if (q.unassigned) params.set('unassigned', 'true');
    if (q.page) params.set('page', String(q.page));
    if (q.pageSize) params.set('pageSize', String(q.pageSize));
    const qs = params.toString();
    return api<StudentsResult>(`/catalog/students${qs ? `?${qs}` : ''}`);
  },
  /** Gán (hoặc bỏ gán khi `classId` là `null`) lớp cho một học viên. */
  setStudentClass: (userId: string, classId: string | null) =>
    api<StudentItem>(`/catalog/students/${userId}/class`, {
      method: 'PUT',
      body: { classId },
    }),
  /** Xếp hàng loạt học viên vào một lớp. Trả số đã xếp và số bị bỏ qua. */
  assignClass: (classId: string, userIds: string[]) =>
    api<{ updated: number; skipped: number }>('/catalog/students/assign-class', {
      method: 'POST',
      body: { classId, userIds },
    }),
};
