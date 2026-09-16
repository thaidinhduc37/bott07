import { useEffect, useRef, useState } from 'react';
import mammoth from 'mammoth';

/** Nhãn duy nhất cố định trong mọi mẫu đơn cho ô chữ ký của người lập đơn —
 * xem `OWNER_SIGNATURE_TITLE` trong `server/app/services/docx_renderer.py`.
 * Dò đúng chữ này trong bản xem trước để tô sáng, không phải đoán vị trí. */
const OWNER_SIGNATURE_TITLE = 'HỌC VIÊN VIẾT ĐƠN';

/**
 * Xem trước bản in (.docx) ngay trong trang — không cần tải file xuống mở
 * bằng Word mới biết đơn trông ra sao trước khi ký. Chuyển .docx sang HTML
 * hoàn toàn ở trình duyệt (mammoth.js đọc thẳng file nhị phân đã tải về);
 * không cần thêm gì ở backend, và không tạo ra bản PDF trung gian phải quản
 * lý vòng đời riêng.
 *
 * Khung nhìn kiểu OnlyOffice (thanh công cụ mỏng + trang giấy nổi trên nền
 * xám) — thuần CSS cho quen mắt với phần mềm soạn thảo văn bản, KHÔNG phải
 * một trình soạn thảo thật: không có công cụ nào trên thanh đó bấm được.
 *
 * Đây là bản xem trước xấp xỉ — mammoth giữ chữ đậm/nghiêng/bảng nhưng bỏ
 * qua bố cục trang (lề, ngắt trang, phông chữ chính xác). Muốn đúng-từng-
 * pixel thì phải tải file thật.
 */
export function DocumentPreview({ url, fileName }: { url: string; fileName?: string }) {
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const pageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setHtml(null);

    fetch(url, { credentials: 'include' })
      .then((r) => {
        if (!r.ok) throw new Error('Không tải được file để xem trước');
        return r.arrayBuffer();
      })
      .then((buf) => mammoth.convertToHtml({ arrayBuffer: buf }))
      .then((result) => {
        if (!cancelled) setHtml(result.value);
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [url]);

  // Tô sáng đúng ô chữ ký của người lập đơn — dò theo chữ, không theo vị trí
  // (bản mammoth dựng lại bảng nên số hàng/cột có thể lệch so với file gốc).
  useEffect(() => {
    if (!html || !pageRef.current) return;
    const cells = pageRef.current.querySelectorAll('td, th');
    for (const cell of cells) {
      if (cell.textContent?.toUpperCase().includes(OWNER_SIGNATURE_TITLE)) {
        cell.classList.add('doc-preview__sign-zone');
      }
    }
  }, [html]);

  if (loading) return <p className="eyebrow">Đang dựng bản xem trước…</p>;
  if (error) {
    return (
      <div className="notice notice--error" role="alert">
        {error}
      </div>
    );
  }

  return (
    <div className="doc-preview">
      <div className="doc-preview__toolbar">
        <span className="doc-preview__toolbar-file">{fileName ?? 'Bản in'}</span>
        <span className="doc-preview__toolbar-zoom">100%</span>
      </div>
      <div className="doc-preview__canvas">
        <div ref={pageRef} className="doc-preview__page" dangerouslySetInnerHTML={{ __html: html ?? '' }} />
      </div>
      <p style={{ fontSize: '0.6875rem', color: 'var(--ink-faint)', margin: 'var(--gap-3) 0 0' }}>
        Bản xem trước xấp xỉ (không giữ lề/ngắt trang). Tải file để xem đúng bản in.
      </p>
    </div>
  );
}
