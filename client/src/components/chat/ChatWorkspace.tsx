import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError } from '@/services/api';
import {
  chatApi,
  type AssistantMessage,
  type ChatMode,
  type Conversation,
  type CourseRef,
  type Message,
} from '@/services/chat-api';
import { Icon } from '@/components/shared/Icon';
import { AnswerCard } from './AnswerCard';
import { PageHeader } from '@/components/shared/PageHeader';

const MODE_LABEL: Record<ChatMode, string> = {
  QUYCHE: 'Quy chế học tập',
  GIAOTRINH: 'Giáo trình & đề cương',
};

const MODE_HINT: Record<ChatMode, string> = {
  QUYCHE: 'Điều kiện lên lớp, xử lý kết quả học tập, nghỉ học, xét tốt nghiệp…',
  GIAOTRINH: 'Khái niệm, định nghĩa và nội dung trong giáo trình môn học',
};

/**
 * Câu hỏi mẫu bấm được.
 *
 * Không phải trang trí. Hệ thống có một hạn chế đã biết và chưa xử lý được:
 * truy vấn gõ **không dấu** sẽ trượt truy xuất, vì corpus có dấu đầy đủ. Dòng
 * chữ nhắc "gõ có dấu" ở dưới ô nhập là lời khuyên; một câu hỏi bấm được là
 * bằng chứng — người dùng lần đầu thấy ngay dạng câu hỏi nào cho ra kết quả.
 *
 * Cũng giải quyết vấn đề trang trắng: người mới không biết hệ thống *biết* gì,
 * và một ô nhập trống không nói cho họ điều đó.
 */
const SUGGESTIONS: Record<ChatMode, string[]> = {
  QUYCHE: [
    'Học viên bị buộc thôi học trong những trường hợp nào?',
    'Điều kiện để được dự thi kết thúc học phần là gì?',
    'Nghỉ học quá bao nhiêu buổi thì không được thi?',
    'Cách tính điểm trung bình chung học kỳ?',
  ],
  GIAOTRINH: [
    'Khóa chính trong mô hình quan hệ là gì?',
    'Phân biệt khóa chính và khóa ngoại',
    'Chuẩn hóa cơ sở dữ liệu dạng 3NF nghĩa là gì?',
  ],
};

export function ChatWorkspace({ rail }: { rail?: ReactNode } = {}) {
  const [mode, setMode] = useState<ChatMode>('QUYCHE');
  const [modesReady, setModesReady] = useState<Record<ChatMode, { ready: boolean; documents: number }> | null>(null);
  const [courses, setCourses] = useState<CourseRef[]>([]);
  const [courseId, setCourseId] = useState<string>('');

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);

  const [sideTab, setSideTab] = useState<'history' | 'info'>('history');
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);

  // Khai báo TRƯỚC effect dùng tới nó: đặt sau thì effect tham chiếu một `const`
  // chưa khởi tạo ở thời điểm dựng, và chỉ chạy được nhờ effect được hoãn tới
  // sau khi render xong — một chỗ dựa quá mỏng.
  const refreshConversations = useCallback(async () => {
    try {
      const r = await chatApi.conversations();
      setConversations(r.items);
    } catch {
      /* danh sách hội thoại không quan trọng bằng việc hỏi được */
    }
  }, []);

  useEffect(() => {
    void chatApi
      .modes()
      .then(setModesReady)
      .catch(() => setModesReady(null));
    void chatApi
      .courses()
      .then((r) => setCourses(r.items))
      .catch(() => setCourses([]));
    void refreshConversations();
  }, [refreshConversations]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, busy]);

  async function openConversation(id: string) {
    setError(null);
    try {
      const c = await chatApi.conversation(id);
      setConversationId(c.id);
      setMode(c.mode);
      setMessages(c.messages);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Không mở được hội thoại');
    }
  }

  function startNew(newMode?: ChatMode) {
    setConversationId(null);
    setMessages([]);
    setError(null);
    if (newMode) {
      setMode(newMode);
    }
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || busy) return;

    setError(null);
    setBusy(true);
    // Hiện câu hỏi ngay, không đợi máy chủ. Một truy vấn đi qua tối đa sáu lượt
    // gọi mô hình và có thể mất vài chục giây; để ô nhập trống suốt thời gian đó
    // khiến người dùng tưởng thao tác không ăn.
    const optimistic: Message = {
      id: `tam-${Date.now()}`,
      role: 'USER',
      content: q,
      createdAt: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);
    setQuestion('');

    try {
      const res = await chatApi.ask({
        question: q,
        mode,
        conversationId: conversationId ?? undefined,
        courseId: mode === 'GIAOTRINH' && courseId ? courseId : undefined,
      });
      setConversationId(res.conversationId);
      setMessages((prev) => [...prev, res.message as AssistantMessage]);
      void refreshConversations();
    } catch (e) {
      // Gỡ câu hỏi lạc quan ra: nó không được lưu ở máy chủ, giữ lại sẽ khiến
      // lịch sử trên màn hình khác với lịch sử thật.
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      setQuestion(q);
      if (e instanceof ApiError) {
        setError(
          e.status === 429
            ? 'Bạn đã hỏi quá nhanh. Đợi một chút rồi thử lại.'
            : e.status === 409
              ? 'Chưa có tài liệu nào được nạp cho chế độ này. Liên hệ cán bộ quản lý đào tạo.'
              : e.message,
        );
      } else {
        setError('Không kết nối được tới máy chủ.');
      }
    } finally {
      setBusy(false);
    }
  }

  const modeReady = modesReady?.[mode]?.ready ?? true;

  return (
    <div className={`chat-layout shell--wide`}>
      {/* --------------------------------------------------- lịch sử hội thoại

          Cột trái cố định, giống danh sách hội thoại của mọi ứng dụng chat —
          không phải một danh sách rời nằm dưới ô nhập như bản trước. Luôn hiện
          (kể cả rỗng) để cột không nhảy bề rộng khi hội thoại đầu tiên xuất
          hiện. */}
      <aside className="chat-side">
        {rail && (
          <div className="chat-side__tabs" role="tablist" aria-label="Bảng bên">
            {(
              [
                ['history', 'Hội thoại'],
                ['info', 'Thông tin'],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={sideTab === id}
                className={`chat-side__tab${sideTab === id ? ' chat-side__tab--on' : ''}`}
                onClick={() => setSideTab(id)}
              >
                {label}
              </button>
            ))}
          </div>
        )}
        {(!rail || sideTab === 'history') && (
          <div className="chat-history">
            <div className="chat-history__head">
              <span className="eyebrow">Hội thoại</span>
              <div style={{ display: 'flex', gap: 'var(--gap-1)' }}>
                <button
                  type="button"
                  className="btn btn--ghost btn--icon"
                  onClick={() => startNew('QUYCHE')}
                  title="Hỏi quy chế"
                >
                  <Icon name="plus" size={16} />
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--icon"
                  onClick={() => startNew('GIAOTRINH')}
                  title="Hỏi giáo trình"
                >
                  <Icon name="book" size={16} />
                </button>
              </div>
            </div>
            {conversations.length === 0 ? (
              <p className="chat-history__empty">Chưa có hội thoại nào.</p>
            ) : (
              <div className="chat-history__sections">
                {(() => {
                  const quyche = conversations.filter((c) => c.mode === 'QUYCHE');
                  const giaotrinh = conversations.filter((c) => c.mode === 'GIAOTRINH');
                  return (
                    <>
                      {quyche.length > 0 && (
                        <div className="chat-history__section">
                          <button
                            type="button"
                            className="chat-history__section-title"
                            onClick={() => startNew('QUYCHE')}
                          >
                            Quy chế học tập
                          </button>
                          <ul className="chat-history__list">
                            {quyche.map((c) => (
                              <li key={c.id}>
                                <button
                                  type="button"
                                  className={`chat-history__item${c.id === conversationId ? ' chat-history__item--on' : ''}`}
                                  onClick={() => void openConversation(c.id)}
                                >
                                  <span className="chat-history__title">{c.title ?? 'Hội thoại không tên'}</span>
                                  <span className="chat-history__meta">{c.messageCount} tin nhắn</span>
                                </button>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {giaotrinh.length > 0 && (
                        <div className="chat-history__section">
                          <button
                            type="button"
                            className="chat-history__section-title"
                            onClick={() => startNew('GIAOTRINH')}
                          >
                            Trợ lý học tập
                          </button>
                          <ul className="chat-history__list">
                            {giaotrinh.map((c) => (
                              <li key={c.id}>
                                <button
                                  type="button"
                                  className={`chat-history__item${c.id === conversationId ? ' chat-history__item--on' : ''}`}
                                  onClick={() => void openConversation(c.id)}
                                >
                                  <span className="chat-history__title">{c.title ?? 'Hội thoại không tên'}</span>
                                  <span className="chat-history__meta">{c.messageCount} tin nhắn</span>
                                </button>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            )}
          </div>
        )}
        {rail && sideTab === 'info' && rail}
      </aside>

      <div className="chat-main">
        <div className="stack chat-scroll">
          <PageHeader title={MODE_LABEL[mode]} description={MODE_HINT[mode]} />

          {mode === 'GIAOTRINH' && courses.length > 0 && (
            <div className="field" style={{ maxWidth: '26rem' }}>
              <label className="field__label" htmlFor="mon-hoc">
                Giới hạn theo môn học
              </label>
              <select
                id="mon-hoc"
                className="field__input"
                value={courseId}
                onChange={(e) => setCourseId(e.target.value)}
              >
                <option value="">Tất cả môn có tài liệu</option>
                {courses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code} — {c.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {!modeReady && (
            <div className="notice notice--warn">
              Chưa có tài liệu nào được nạp cho mục "{MODE_LABEL[mode]}". Cán bộ quản lý đào tạo cần nạp tài liệu trước
              khi mục này dùng được.
            </div>
          )}

          {/* ---------------------------------------------------------- hội thoại

          Chỉ dựng khối này khi có gì để hiện. Một `<div>` rỗng vẫn là một ô
          trong lưới, nên nó vẫn ăn hai khoảng cách — và trên màn hình chưa hỏi
          gì, hai khoảng cách đó thành một mảng trống giữa thẻ chọn chế độ và ô
          nhập, trông như phần nội dung bị hỏng. */}
          {/* Trạng thái ban đầu: gợi ý câu hỏi nằm ngay vùng trống phía trên ô nhập, thay vì chen vào ô nhập. */}
          {messages.length === 0 && !busy && modeReady && (
            <section className="chat-empty" aria-label="Gợi ý câu hỏi">
              <h2 className="chat-empty__h">Bạn muốn hỏi gì?</h2>
              <ul className="chat-empty__list">
                {SUGGESTIONS[mode].map((q) => (
                  <li key={q}>
                    <button type="button" className="chat-empty__item" onClick={() => setQuestion(q)}>
                      <Icon name="chat" size={16} />
                      <span>{q}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {(messages.length > 0 || busy) && (
            <div className="thread">
              {messages.map((m) =>
                m.role === 'USER' ? (
                  <p key={m.id} className="bubble">
                    {m.content}
                  </p>
                ) : (
                  <AnswerCard key={m.id} message={m} />
                ),
              )}

              {/* Khung chờ thay cho dòng chữ "Đang tải".

            Một truy vấn đi qua tối đa sáu lượt gọi mô hình và bước xếp hạng chạy
            trên CPU, nên chờ vài chục giây là bình thường. Khung xám nhấp nháy
            giữ đúng chỗ của câu trả lời sắp tới, nên khi nó về, trang không nhảy
            — và nó nói được "đang chạy" mà không cần người dùng đọc chữ. */}
              {busy && (
                <div className="sheet sheet--evidence" style={{ padding: 'var(--gap-5)' }} aria-live="polite">
                  <span className="sr-only">Đang tìm câu trả lời</span>
                  <div className="skeleton" style={{ height: '0.9rem', width: '92%' }} />
                  <div className="skeleton" style={{ height: '0.9rem', width: '100%', marginTop: '0.6rem' }} />
                  <div className="skeleton" style={{ height: '0.9rem', width: '64%', marginTop: '0.6rem' }} />
                  <p style={{ margin: 'var(--gap-4) 0 0', fontSize: '0.8125rem', color: 'var(--ink-faint)' }}>
                    Truy xuất tài liệu, xếp hạng đoạn liên quan, kiểm tra đủ căn cứ rồi mới soạn câu trả lời. Bước xếp
                    hạng chạy trên CPU nên có thể mất vài chục giây.
                  </p>
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          )}

          {error && (
            <div className="notice notice--error" role="alert">
              {error}
            </div>
          )}
        </div>

        {/* ------------------------------------------------------------ ô nhập

          Chân cố định của cột chat — không cuộn theo nội dung, không "nhảy"
          khi khung chờ/câu trả lời xuất hiện. `.chat-scroll` ở trên là phần
          duy nhất cuộn; ô nhập luôn đứng yên tại đáy khung nhìn. */}
        <form onSubmit={send} className="sheet ask">
          {/* Câu hỏi mẫu chỉ hiện khi hội thoại còn trống. Sau tin nhắn đầu tiên
            người dùng đã biết cách hỏi, và giữ chúng lại chỉ chiếm chỗ của thứ
            họ đang thực sự đọc. */}
          <label className="sr-only" htmlFor="cau-hoi">
            Câu hỏi của bạn
          </label>
          <textarea
            id="cau-hoi"
            className="field__input"
            rows={2}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              // Enter gửi câu hỏi — chuẩn của mọi ô chat. Shift+Enter mới xuống
              // dòng, vì đó là lúc người dùng chủ động muốn thêm một dòng chứ
              // không phải gửi ngay.
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void send(e as unknown as React.FormEvent);
              }
            }}
            disabled={busy || !modeReady}
            maxLength={2000}
            placeholder={
              mode === 'QUYCHE'
                ? 'Ví dụ: Học viên bị buộc thôi học trong những trường hợp nào?'
                : 'Ví dụ: Khóa chính trong mô hình quan hệ là gì?'
            }
          />
          <div className="spread" style={{ marginTop: 'var(--gap-3)' }}>
            <span className="field__hint" style={{ maxWidth: '34rem' }}>
              Gõ tiếng Việt có dấu để tìm đúng — tài liệu gốc có dấu đầy đủ. Enter để gửi, Shift+Enter để xuống dòng.
            </span>
            <div className="row">
              {messages.length > 0 && (
                <button type="button" className="btn btn--ghost" onClick={() => startNew()} disabled={busy}>
                  Hội thoại mới
                </button>
              )}
              <button type="submit" className="btn btn--primary" disabled={busy || !question.trim() || !modeReady}>
                <Icon name="send" size={15} />
                {busy ? 'Đang tìm…' : 'Gửi câu hỏi'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
