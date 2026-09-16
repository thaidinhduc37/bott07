import { ChatWorkspace } from '@/components/chat/ChatWorkspace';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';

export default function StudentChatPage() {
  useDocumentTitle('Hỏi đáp');
  return <ChatWorkspace />;
}
