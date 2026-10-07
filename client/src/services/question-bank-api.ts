import { API_URL, api } from './api';
import type { ImportResult } from './grades-staff-api';

/**
 * Ngân hàng câu hỏi (giảng viên / quản lý), xem `server/app/routers/question_bank.py`:
 *  - `GET    /question-bank/courses`                   → môn được quản lý + số câu
 *  - `GET    /question-bank/questions?courseId=&page=` → danh sách (có đáp án)
 *  - `DELETE /question-bank/questions/{id}`
 *  - `POST   /question-bank/import?courseId=&format=gift|csv&dryRun=` → ImportResult (multipart)
 */

export interface BankCourse {
  id: string;
  code: string;
  name: string;
  questionCount: number;
}

export interface BankQuestion {
  id: string;
  question: string;
  options: string[];
  correctIndex: number;
  /** Mọi đáp án đúng (≥ 2 phần tử = câu nhiều đáp án đúng). */
  correctIndexes: number[];
  explanation: string;
  chapter: string | null;
}

export const questionBankApi = {
  courses: () => api<{ items: BankCourse[] }>('/question-bank/courses'),

  questions: (courseId: string, page: number, pageSize = 20) =>
    api<{ total: number; page: number; pageSize: number; items: BankQuestion[] }>(
      `/question-bank/questions?courseId=${courseId}&page=${page}&pageSize=${pageSize}`,
    ),

  remove: (id: string) => api<{ message: string }>(`/question-bank/questions/${id}`, { method: 'DELETE' }),

  import: async (courseId: string, file: File, dryRun: boolean, format: 'gift' | 'csv'): Promise<ImportResult> => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(
      `${API_URL}/question-bank/import?courseId=${courseId}&format=${format}${dryRun ? '&dryRun=true' : ''}`,
      {
        method: 'POST',
        credentials: 'include',
        body: form,
      },
    );
    const body = (await res.json().catch(() => null)) as { message?: string } | ImportResult | null;
    if (!res.ok) {
      const msg = body && 'message' in body && typeof body.message === 'string' ? body.message : 'Nạp tệp thất bại';
      throw new Error(msg);
    }
    return body as ImportResult;
  },
};
