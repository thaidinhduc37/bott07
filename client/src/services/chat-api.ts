import { api } from './api';

export type ChatMode = 'QUYCHE' | 'GIAOTRINH';

export interface Citation {
  marker: number;
  documentId: string | null;
  documentTitle: string;
  sourceFile: string;
  page: number | null;
  articleNumber: string | null;
  articleRange?: string | null;
  rerankScore: number | null;
  snippet: string | null;
}

export interface RetrievedChunk {
  rank: number;
  score: number;
  source_file: string;
  page: number | null;
  article_number: string | null;
  document_title: string;
  text: string;
  cited: boolean;
}

/** Phản hồi của chính người dùng về một câu trả lời. */
export interface MessageFeedback {
  rating: 'UP' | 'DOWN';
  reason: string | null;
  comment: string | null;
}

export interface AssistantMessage {
  id: string;
  role: 'ASSISTANT';
  content: string;
  /** Pipeline đã từ chối trả lời vì không đủ căn cứ. */
  abstained: boolean;
  abstainReason: string | null;
  /** Điểm cross-encoder cao nhất, và ngưỡng nó bị so với. */
  confidence: number | null;
  threshold: number | null;
  /** Kết quả kiểm chứng groundedness. `null` = không phân tích được. */
  grounded: boolean | null;
  route: string | null;
  rounds: number | null;
  latencyMs: number | null;
  trace: string[] | null;
  citations: Citation[];
  retrievedChunks: RetrievedChunk[] | null;
  /** Đánh giá của chính bạn (chỉ có khi tải lại lịch sử hội thoại). */
  feedback?: MessageFeedback | null;
  createdAt: string;
}

export interface UserMessage {
  id: string;
  role: 'USER';
  content: string;
  createdAt: string;
}

export type Message = UserMessage | AssistantMessage;

export interface Conversation {
  id: string;
  title: string | null;
  mode: ChatMode;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
}

export interface CourseRef {
  id: string;
  code: string;
  name: string;
}

export const chatApi = {
  ask: (body: { question: string; mode: ChatMode; conversationId?: string; courseId?: string }) =>
    api<{ conversationId: string; message: AssistantMessage }>('/chat/ask', {
      method: 'POST',
      body,
    }),

  modes: () =>
    api<Record<ChatMode, { ready: boolean; documents: number }>>('/chat/modes'),

  courses: () => api<{ items: CourseRef[] }>('/chat/courses'),

  conversations: () => api<{ items: Conversation[]; total: number }>('/chat/conversations'),

  conversation: (id: string) =>
    api<{ id: string; title: string | null; mode: ChatMode; messages: Message[] }>(
      `/chat/conversations/${id}`,
    ),

  remove: (id: string) => api<{ message: string }>(`/chat/conversations/${id}`, { method: 'DELETE' }),

  /** `rating: null` = bỏ đánh giá. `reason` chỉ có nghĩa với `DOWN`. */
  feedback: (messageId: string, body: { rating: 'UP' | 'DOWN' | null; reason?: string; comment?: string }) =>
    api<{ feedback: MessageFeedback | null }>(`/chat/messages/${messageId}/feedback`, { method: 'PUT', body }),
};
