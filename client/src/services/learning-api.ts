import { api } from './api';
import type { CourseRef } from './chat-api';

export interface QuizQuestion {
  id: string;
  ordinal: number;
  question: string;
  options: string[];
  /** Câu có nhiều đáp án đúng: hiện ô tick (không báo trước có mấy đáp án đúng). */
  multi: boolean;
  /** Câu lấy lại từ sổ câu sai, không phải câu mới sinh. */
  fromReview: boolean;
  // Chỉ có sau khi nộp bài — backend không gửi đáp án trước.
  correctIndex?: number;
  correctIndexes?: number[];
  selectedIndexes?: number[];
  explanation?: string;
  sourceFile?: string | null;
  sourcePage?: number | null;
  selectedIndex?: number | null;
  isCorrect?: boolean | null;
}

export interface QuizSession {
  id: string;
  /** `null` = lượt ôn câu sai. */
  topic: string | null;
  course: CourseRef | null;
  status: 'IN_PROGRESS' | 'SUBMITTED';
  score: number | null;
  feedback: string | null;
  confidence: number | null;
  submittedAt: string | null;
  createdAt: string;
  questions: QuizQuestion[];
}

export interface QuizSummary {
  id: string;
  topic: string | null;
  course: CourseRef | null;
  status: QuizSession['status'];
  score: number | null;
  questionCount: number;
  submittedAt: string | null;
  createdAt: string;
}

export type CreateQuizResult =
  | { abstained: true; reason: string | null; confidence: number; threshold: number }
  | { abstained: false; session: QuizSession };

export interface ReviewItem {
  id: string;
  course: CourseRef | null;
  question: string;
  options: string[];
  correctIndex: number;
  correctIndexes: number[];
  explanation: string;
  sourceFile: string | null;
  sourcePage: number | null;
  box: number;
  dueAt: string | null;
  isDue: boolean;
  mastered: boolean;
  timesWrong: number;
  timesRight: number;
}

export interface ReviewOverview {
  due: number;
  learning: number;
  mastered: number;
  items: ReviewItem[];
}

export interface NoteCitation {
  marker: number;
  documentTitle: string | null;
  sourceFile: string | null;
  page: number | null;
  articleNumber: string | null;
  snippet: string | null;
}

export interface StudyNote {
  id: string;
  sourceType: 'CHAT' | 'QUIZ' | 'MANUAL';
  sourceId: string | null;
  course: CourseRef | null;
  title: string;
  content: string;
  citations: NoteCitation[];
  /** Ghi chú riêng của học viên — phần duy nhất sửa được với ghi chú chép từ nguồn. */
  note: string | null;
  pinned: boolean;
  createdAt: string;
  updatedAt: string;
}

export type Readiness = 'CHUA_ON' | 'CAN_ON_THEM' | 'ON_DINH';

/** Một khoảng ngày liền nhau cùng một việc (`from`..`to`, tính cả hai đầu). */
export interface ExamPlanDay {
  from: string;
  to: string;
  kind: 'DOC' | 'REVIEW' | 'FINAL';
  title: string;
  documentId: string | null;
  suggestedTopic: string | null;
}

export interface ExamPlanItem {
  id: string;
  course: CourseRef;
  examDate: string;
  startsAt: string;
  durationMinutes: number;
  room: string;
  building: string | null;
  format: string;
  formatLabel: string;
  allowedMaterials: string | null;
  daysLeft: number;
  materials: { id: string; title: string }[];
  progress: {
    quizCount: number;
    avgScore: number | null;
    reviewDue: number;
    reviewLearning: number;
    readiness: Readiness;
  };
  plan: ExamPlanDay[];
}

export const learningApi = {
  createQuiz: (body: { topic?: string; courseId?: string; nQuestions?: number; source?: 'ai' | 'bank' }) =>
    api<CreateQuizResult>('/learning/quiz', { method: 'POST', body }),

  /** Môn nào đã có ngân hàng câu hỏi của giảng viên, kèm số câu. */
  bank: () => api<{ items: { courseId: string; count: number }[] }>('/learning/bank'),

  createReview: (body: { courseId?: string; limit?: number } = {}) =>
    api<QuizSession>('/learning/review', { method: 'POST', body }),

  sessions: () => api<{ items: QuizSummary[]; total: number }>('/learning/quiz'),

  session: (id: string) => api<QuizSession>(`/learning/quiz/${id}`),

  submit: (id: string, answers: { questionId: string; selectedIndex?: number | null; selectedIndexes?: number[] }[]) =>
    api<QuizSession>(`/learning/quiz/${id}/submit`, { method: 'POST', body: { answers } }),

  progress: () => api<ProgressOverview>('/learning/progress'),

  reviewItems: () => api<ReviewOverview>('/learning/review-items'),

  removeReviewItem: (id: string) => api<{ message: string }>(`/learning/review-items/${id}`, { method: 'DELETE' }),

  examPlan: () => api<{ today: string; exams: ExamPlanItem[]; reason?: 'NO_CLASS' }>('/learning/exam-plan'),

  notes: (params: { q?: string; courseId?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set('q', params.q);
    if (params.courseId) qs.set('courseId', params.courseId);
    const suffix = qs.toString() ? `?${qs}` : '';
    return api<{ items: StudyNote[]; total: number }>(`/learning/notes${suffix}`);
  },

  createNote: (body: { title: string; content: string; courseId?: string }) =>
    api<StudyNote>('/learning/notes', { method: 'POST', body }),

  noteFromChat: (body: { sourceId: string; courseId?: string; note?: string }) =>
    api<StudyNote>('/learning/notes/from-chat', { method: 'POST', body }),

  noteFromQuiz: (body: { sourceId: string; note?: string }) =>
    api<StudyNote>('/learning/notes/from-quiz', { method: 'POST', body }),

  updateNote: (id: string, body: { title?: string; content?: string; note?: string | null; pinned?: boolean }) =>
    api<StudyNote>(`/learning/notes/${id}`, { method: 'PATCH', body }),

  removeNote: (id: string) => api<{ message: string }>(`/learning/notes/${id}`, { method: 'DELETE' }),
};

// ---- tiến trình học viên & thống kê giảng viên

export interface ProgressCourse {
  course: { id: string; code: string; name: string };
  sessions: number;
  avgScore: number | null;
  lastScore: number | null;
  reviewDue: number;
  mastered: number;
  wrongTotal: number;
}

export interface ProgressOverview {
  week: { sessions: number; avgScore: number | null };
  streakDays: number;
  totalSessions: number;
  activity: { date: string; count: number }[];
  review: { due: number; learning: number; mastered: number };
  courses: ProgressCourse[];
}

export interface InsightCourse {
  course: { id: string; code: string; name: string };
  sessions: number;
  learners: number;
  avgScore: number | null;
}

export interface InsightCourseDetail {
  course: { id: string; code: string; name: string };
  windowDays: number;
  minLearners: number;
  hardQuestions: {
    question: string;
    correctAnswer: string | null;
    sourceFile: string | null;
    sourcePage: number | null;
    learners: number;
    timesWrong: number;
  }[];
  topics: { topic: string; sessions: number; learners: number; avgScore: number | null }[];
}

export interface UnansweredQuestion {
  question: string;
  mode: string;
  confidence: number | null;
  createdAt: string;
}

export interface FeedbackReview {
  windowDays: number;
  up: number;
  down: number;
  /** Tỉ lệ hữu ích 0–1; null khi chưa có phản hồi nào. */
  helpfulRate: number | null;
  byReason: { reason: string; label: string; count: number }[];
  items: {
    question: string | null;
    answer: string;
    abstained: boolean;
    mode: string;
    confidence: number | null;
    reason: string | null;
    reasonLabel: string | null;
    comment: string | null;
    createdAt: string;
  }[];
}

export const insightsApi = {
  courses: () => api<{ windowDays: number; items: InsightCourse[] }>('/learning/insights/courses'),
  course: (id: string) => api<InsightCourseDetail>(`/learning/insights/courses/${id}`),
  feedback: (limit = 30) => api<FeedbackReview>(`/learning/insights/feedback?limit=${limit}`),
  unanswered: (limit = 30) =>
    api<{ windowDays: number; items: UnansweredQuestion[] }>(`/learning/insights/unanswered?limit=${limit}`),
};
