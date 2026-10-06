import { api } from './api';

export interface SupportProcedure {
  code: string;
  name: string;
  description: string | null;
  approvalSteps: { order: number; title: string }[];
  /** Các ô học viên phải tự điền (thông tin lấy sẵn từ hồ sơ không có trong danh sách). */
  fields: { label: string; required: boolean }[];
}

export interface SupportContact {
  name: string;
  role: string;
  email?: string;
  phone?: string;
  location?: string;
  hours?: string;
}

export interface SupportGuide {
  procedures: SupportProcedure[];
  contacts: SupportContact[];
  faq: { q: string; a: string }[];
}

export const supportApi = {
  guide: () => api<SupportGuide>('/support/guide'),
};
