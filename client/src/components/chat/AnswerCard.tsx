import { useState } from 'react';
import { Icon } from '@/components/shared/Icon';
import { SaveToNotebook } from '@/components/shared/SaveToNotebook';
import type { AssistantMessage, Citation } from '@/services/chat-api';
import { AnswerFeedback } from './AnswerFeedback';
import { learningApi } from '@/services/learning-api';

/** Vị trí của một trích dẫn: quy chế theo điều, giáo trình theo trang. Đoạn trải nhiều điều thì ghi dải ("Điều 17–20"): chỉ ghi một điều là trích dẫn sai khó phát hiện. */
function locator(c: Citation): string {
  const parts: string[] = [];
  if (c.articleRange) parts.push(c.articleRange);
  else if (c.articleNumber) parts.push(c.articleNumber);
  if (c.page) parts.push(`trang ${c.page}`);
  return parts.join(' · ') || 'không rõ vị trí';
}

/**
 * Dựng nội dung câu trả lời: `[1]`, `[2]` thành nút neo tới khối trích dẫn bên dưới và `**…**` thành chữ đậm (mô hình luôn trả
 * Markdown). Cố ý không hiển thị Markdown đầy đủ, chỉ đúng quy tắc mô hình thật sự sinh ra: thêm bảng, liên kết, tiêu đề là mở cửa không ai cần.
 */
const TOKEN = /(\*\*[^*\n]+\*\*|\[\d+\])/g;

function renderInline(text: string, onJump: (marker: number) => void, keyPrefix: string) {
  return text.split(TOKEN).map((part, i) => {
    const bold = /^\*\*([^*\n]+)\*\*$/.exec(part);
    if (bold) return <strong key={`${keyPrefix}-${i}`}>{bold[1]}</strong>;

    const m = /^\[(\d+)\]$/.exec(part);
    if (!m) return <span key={`${keyPrefix}-${i}`}>{part}</span>;

    const n = Number(m[1]);
    return (
      <button
        key={`${keyPrefix}-${i}`}
        type="button"
        className="cite-ref"
        onClick={() => onJump(n)}
        title={`Xem nguồn ${n}`}
      >
        {n}
      </button>
    );
  });
}

const ORDERED_ITEM = /^(\d+)[.)]\s+(.*)$/;
const BULLET_ITEM = /^[-*•]\s+(.*)$/;

type Block =
  | { kind: 'ol'; items: string[] }
  | { kind: 'ul'; items: string[] }
  | { kind: 'p'; lines: string[] };

/**
 * Gom các dòng thô thành đoạn văn, danh sách có thứ tự hoặc danh sách chấm theo tiền tố dòng ("1. ", "- ", "• "). Mô hình trả
 * Markdown tối giản (list phẳng, không lồng) nên không cần trình phân tích Markdown đầy đủ.
 */
function toBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  const lines = text.split('\n');

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;

    const ordered = ORDERED_ITEM.exec(line);
    const bullet = !ordered ? BULLET_ITEM.exec(line) : null;

    if (ordered) {
      const last = blocks[blocks.length - 1];
      if (last?.kind === 'ol') last.items.push(ordered[2]);
      else blocks.push({ kind: 'ol', items: [ordered[2]] });
    } else if (bullet) {
      const last = blocks[blocks.length - 1];
      if (last?.kind === 'ul') last.items.push(bullet[1]);
      else blocks.push({ kind: 'ul', items: [bullet[1]] });
    } else {
      const last = blocks[blocks.length - 1];
      if (last?.kind === 'p') last.lines.push(line);
      else blocks.push({ kind: 'p', lines: [line] });
    }
  }

  return blocks;
}

function renderAnswer(text: string, onJump: (marker: number) => void) {
  return toBlocks(text).map((block, bi) => {
    if (block.kind === 'ol') {
      return (
        <ol className="answer-list" key={`ol-${bi}`}>
          {block.items.map((item, ii) => (
            <li key={ii}>{renderInline(item, onJump, `ol-${bi}-${ii}`)}</li>
          ))}
        </ol>
      );
    }
    if (block.kind === 'ul') {
      return (
        <ul className="answer-list" key={`ul-${bi}`}>
          {block.items.map((item, ii) => (
            <li key={ii}>{renderInline(item, onJump, `ul-${bi}-${ii}`)}</li>
          ))}
        </ul>
      );
    }
    return (
      <p className="answer-p" key={`p-${bi}`}>
        {renderInline(block.lines.join(' '), onJump, `p-${bi}`)}
      </p>
    );
  });
}

export function AnswerCard({ message }: { message: AssistantMessage }) {
  const [openCitations, setOpenCitations] = useState(false);
  const [highlight, setHighlight] = useState<number | null>(null);

  function jumpTo(marker: number) {
    setHighlight(marker);
    // Khối nguồn thu gọn theo mặc định, nên phần tử cần cuộn tới có thể chưa
    // tồn tại trong DOM lúc này. Mở ra trước, rồi đợi một nhịp vẽ để trình
    // duyệt dựng xong trước khi cuộn tới — cuộn ngay trong cùng lượt render sẽ
    // nhắm vào một phần tử chưa có mặt.
    setOpenCitations(true);
    requestAnimationFrame(() => {
      document.getElementById(`nguon-${message.id}-${marker}`)?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    });
  }

  return (
    // Nẹp trái màu mực: đây là khối *bằng chứng*, thứ người dùng in ra và đối
    // chiếu. Không thẻ nào khác trong ứng dụng có nẹp này, nên nó nhận ra được
    // từ xa mà không cần đọc chữ.
    <article className="sheet sheet--evidence" style={{ padding: 'var(--gap-5)' }}>
      {message.abstained ? (
        <div className="notice notice--warn" style={{ marginBottom: 'var(--gap-4)' }}>
          <strong>Không đủ căn cứ để trả lời.</strong>
          <p style={{ margin: '0.35rem 0 0' }}>{message.content}</p>
          {message.abstainReason && (
            <p style={{ margin: '0.5rem 0 0', fontSize: '0.8125rem', opacity: 0.85 }}>
              {message.abstainReason}
            </p>
          )}
        </div>
      ) : (
        <div className="answer-body">{renderAnswer(message.content, jumpTo)}</div>
      )}

      {/* nguồn: thu gọn theo mặc định vì mỗi khối mang cả đoạn nguyên gốc; số nguồn vẫn hiện trên nút, và bấm `[n]` trong câu trả lời (`jumpTo`) tự mở khối này. */}
      {message.citations.length > 0 && (
        <section style={{ marginTop: 'var(--gap-5)' }}>
          <button
            type="button"
            className="btn--quiet"
            onClick={() => setOpenCitations((v) => !v)}
            aria-expanded={openCitations}
          >
            {openCitations ? 'Ẩn' : 'Xem'} nguồn được trích dẫn ({message.citations.length})
          </button>
          {openCitations && (
          <>
          {/* Trích dẫn là khối có nền riêng, không phải dòng danh sách. Đây là
              thứ phân biệt hệ thống này với một chatbot: nó phải nhìn ra được
              ngay từ xa, chứ không phải đọc kỹ mới thấy. */}
          <ol style={{ listStyle: 'none', margin: 'var(--gap-3) 0 0', padding: 0 }}>
            {message.citations.map((c) => (
              <li
                key={c.marker}
                id={`nguon-${message.id}-${c.marker}`}
                className={`cite${highlight === c.marker ? ' cite--focus' : ''}`}
              >
                <span className="cite__marker" aria-hidden="true">
                  <Icon name="quote" size={14} />
                </span>
                <div>
                  <div className="cite__title">
                    <span className="mono" style={{ marginRight: '0.4rem' }}>
                      [{c.marker}]
                    </span>
                    {c.documentTitle}
                  </div>
                  <div className="cite__meta">
                    {locator(c)}
                    {c.rerankScore !== null && (
                      <span className="mono" style={{ marginLeft: '0.6rem', color: 'var(--ink-faint)' }}>
                        độ khớp {c.rerankScore.toFixed(3)}
                      </span>
                    )}
                  </div>
                  {c.snippet && (
                    <p className="cite__snippet">
                      {c.snippet}
                      {c.snippet.length >= 300 && '…'}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
          </>
          )}
        </section>
      )}

      {!message.abstained && message.citations.length === 0 && (
        <div className="notice notice--warn" style={{ marginTop: 'var(--gap-4)' }}>
          Câu trả lời này không kèm trích dẫn nào. Hãy đối chiếu lại với văn bản gốc trước khi dùng.
        </div>
      )}

      {/* Nút lưu câu trả lời vào sổ tay — chỉ khi có câu trả lời thật. */}
      {!message.abstained && (
        <div className="answer-save">
          <SaveToNotebook onSave={() => learningApi.noteFromChat({ sourceId: message.id })} />
        </div>
      )}

      <AnswerFeedback messageId={message.id} initial={message.feedback} abstained={message.abstained} />
    </article>
  );
}
