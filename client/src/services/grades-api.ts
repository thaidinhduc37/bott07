import { api } from './api';

/** Một môn trong một học kỳ, kèm điểm thành phần và điểm học phần. */
export interface GradeCourse {
  courseId: string;
  code: string;
  name: string;
  credits: number;
  /** Điểm thực hành (TH). */
  practice: number | null;
  /** Điểm quá trình (QT). */
  process: number | null;
  /** Điểm giữa kỳ (GK). */
  midterm: number | null;
  /** Điểm cuối kỳ (CK). */
  finalExam: number | null;
  /** Điểm học phần tổng. */
  total: number | null;
  /** `true`/`false` khi đã có điểm; `null` khi chưa nhập. */
  passed: boolean | null;
  note: string | null;
}

/** Một học kỳ: tổng hợp + danh sách môn. */
export interface GradeTerm {
  academicYear: string;
  semester: string;
  credits: number;
  /** Số môn đã có điểm. */
  gradedCount: number;
  /** Tổng số môn trong kỳ. */
  courseCount: number;
  /** Điểm trung bình học kỳ (cân theo tín chỉ). */
  gpa: number | null;
  courses: GradeCourse[];
}

/** Kết quả học tập của học viên hiện tại (`GET /grades/me`). */
export interface AcademicResults {
  /** Điểm từ đó môn được coi là đạt (thang 10). */
  passScore: number;
  summary: {
    creditsStudied: number;
    creditsEarned: number;
    gpa: number | null;
    gpaEarned: number | null;
  };
  terms: GradeTerm[];
}

export const gradesApi = {
  me: () => api<AcademicResults>('/grades/me'),
};
