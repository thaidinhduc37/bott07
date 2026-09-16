import { ChatWorkspace } from '@/components/chat/ChatWorkspace';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';

/**
 * Cán bộ dùng đúng màn hình hỏi đáp của học viên.
 *
 * Không tách thành phiên bản riêng: cán bộ tra cứu quy chế để trả lời học viên,
 * nên họ cần thấy đúng câu trả lời và đúng trích dẫn mà học viên sẽ thấy. Hai
 * giao diện khác nhau ở đây sẽ tạo ra hai "sự thật" khác nhau cho cùng một điều
 * khoản.
 */
export default function StaffChatPage() {
  useDocumentTitle('Hỏi đáp quy chế');
  return <ChatWorkspace />;
}
