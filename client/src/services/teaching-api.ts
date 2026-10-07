import { api } from './api';

/**
 * "Lớp của tôi" của giảng viên (chỉ đọc), xem `server/app/routers/teaching.py`:
 *  - `GET /teaching/classes`      → { items: TeachingClass[] }
 *  - `GET /teaching/classes/{id}` → TeachingClassDetail (404 nếu lớp không thuộc môn mình phụ trách)
 */

export interface TeachingCourse {
  id: string;
  code: string;
  name: string;
  credits: number;
}

export interface TeachingClass {
  id: string;
  code: string;
  name: string;
  faculty: string | null;
  cohortYear: number | null;
  studentCount: number;
  courses: TeachingCourse[];
  /** Buổi dạy gần nhất sắp tới; `null` khi không còn buổi nào. */
  nextSessionAt: string | null;
}

export interface TeachingSession {
  id: string;
  courseId: string;
  courseCode: string;
  courseName: string;
  startsAt: string;
  startPeriod: number;
  endPeriod: number;
  room: string;
  building: string | null;
}

export interface TeachingClassDetail {
  class: { id: string; code: string; name: string; faculty: string | null; cohortYear: number | null };
  courses: TeachingCourse[];
  /** Chỉ mã và họ tên — cùng phạm vi danh sách nhập điểm. */
  students: { studentCode: string; fullName: string }[];
  upcoming: TeachingSession[];
  sections: { courseId: string; academicYear: string; semester: string }[];
}

export const teachingApi = {
  classes: () => api<{ items: TeachingClass[] }>('/teaching/classes'),
  classDetail: (id: string) => api<TeachingClassDetail>(`/teaching/classes/${id}`),
};
