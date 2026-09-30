import { api } from './api';

/**
 * Khoa — CRUD, tổng quan, phân công giảng viên và môn trong phạm vi khoa.
 *
 * Hợp đồng backend (agent E) — JSON camelCase, prefix `/faculties`.
 */

export interface FacultyItem {
  id: string;
  code: string;
  name: string;
  head: { id: string; fullName: string; email: string } | null;
  classCount: number;
  courseCount: number;
  lecturerCount: number;
  studentCount: number;
}

export interface FacultyOverview {
  faculty: FacultyItem;
  classes: { id: string; code: string; name: string; cohortYear: number | null; studentCount: number }[];
  courses: { id: string; code: string; name: string; credits: number; lecturer: { id: string; fullName: string; email: string } | null }[];
  lecturers: { id: string; fullName: string; email: string; courseCount: number }[];
  unassignedCourseCount: number;
}

export interface LecturerCandidate {
  id: string;
  fullName: string;
  email: string;
  facultyId: string | null;
  facultyName: string | null;
}

export interface HeadCandidate {
  id: string;
  fullName: string;
  email: string;
}

export interface FacultyPayload {
  code: string;
  name: string;
  headId?: string | null;
}

export const facultyApi = {
  list: () => api<{ items: FacultyItem[] }>('/faculties'),
  create: (data: FacultyPayload) => api<FacultyItem>('/faculties', { method: 'POST', body: data }),
  update: (id: string, data: Partial<FacultyPayload>) =>
    api<FacultyItem>(`/faculties/${id}`, { method: 'PATCH', body: data }),
  remove: (id: string) => api<{ message: string }>(`/faculties/${id}`, { method: 'DELETE' }),

  overview: (id: string) => api<FacultyOverview>(`/faculties/${id}/overview`),

  lecturerCandidates: () => api<{ items: LecturerCandidate[] }>('/faculties/lecturer-candidates'),
  headCandidates: () => api<{ items: HeadCandidate[] }>('/faculties/head-candidates'),

  addLecturer: (facultyId: string, userId: string) =>
    api<{ message: string }>(`/faculties/${facultyId}/lecturers/${userId}`, { method: 'PUT' }),
  removeLecturer: (facultyId: string, userId: string) =>
    api<{ message: string; unassignedCourses: number }>(
      `/faculties/${facultyId}/lecturers/${userId}`,
      { method: 'DELETE' },
    ),

  assignCourseLecturer: (facultyId: string, courseId: string, lecturerId: string | null) =>
    api<{ id: string; code: string; name: string; credits: number; lecturer: { id: string; fullName: string; email: string } | null }>(
      `/faculties/${facultyId}/courses/${courseId}`,
      { method: 'PUT', body: { lecturerId } },
    ),
};
