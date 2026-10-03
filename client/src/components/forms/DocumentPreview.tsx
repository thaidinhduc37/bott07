import { useEffect, useRef, useState } from 'react';
import { renderAsync } from 'docx-preview';

/** Nhãn duy nhất cố định trong mọi mẫu đơn cho ô chữ ký của người lập đơn —
 * xem `OWNER_SIGNATURE_TITLE` trong `server/app/services/docx_renderer.py`.
 * Dò đúng chữ này trong bản xem trước để tô sáng, không phải đoán vị trí. */
const OWNER_SIGNATURE_TITLE = 'HỌC VIÊN VIẾT ĐƠN';

/** Bề ngang tờ A4 (21 cm) tính bằng px CSS ở 96 dpi. */
const A4_WIDTH_PX = 793.7;

/**
 * Xem trước bản in (.docx) ngay trong trang — không cần tải file xuống mở
 * bằng Word mới biết đơn trông ra sao trước khi ký. Dựng hoàn toàn ở trình
 * duyệt bằng docx-preview: giữ khổ A4, lề, phông, căn lề, thụt đầu dòng, bảng
 * không viền và khối chữ ký đúng như file .docx sẽ in, nên bản xem trước cho
 * thấy đúng thể thức văn bản hành chính. Không cần thêm gì ở backend, và
 * không tạo ra bản PDF trung gian phải quản lý vòng đời riêng.
 *
 * Khung nhìn kiểu OnlyOffice (thanh công cụ mỏng + trang giấy nổi trên nền
 * xám) — thuần CSS cho quen mắt với phần mềm soạn thảo văn bản, KHÔNG phải
 * một trình soạn thảo thật: không có công cụ nào trên thanh đó bấm được.
 */
export function DocumentPreview({ url, fileName }: { url: string; fileName?: string }) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const pageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  // Thu cả tờ A4 cho vừa bề ngang khung xem, thay vì bắt cuộn ngang. Không bao
  // giờ phóng to quá 100%.
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const fit = () => {
      const cs = getComputedStyle(canvas);
      const avail = canvas.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      setZoom(Math.min(1, Math.max(0.3, avail / A4_WIDTH_PX)));
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(canvas);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setReady(false);

    fetch(url, { credentials: 'include' })
      .then((r) => {
        if (!r.ok) throw new Error('Không tải được file để xem trước');
        return r.arrayBuffer();
      })
      .then(async (buf) => {
        const host = pageRef.current;
        if (cancelled || !host) return;
        host.innerHTML = '';
        await renderAsync(buf, host, undefined, {
          className: 'docx',
          inWrapper: true,
          breakPages: true,
          ignoreWidth: false,
          ignoreHeight: false,
          useBase64URL: true,
        });
        if (!cancelled) setReady(true);
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

  // Tô sáng đúng ô chữ ký của người lập đơn — dò theo chữ, không theo vị trí.
  useEffect(() => {
    if (!ready || !pageRef.current) return;
    const cells = pageRef.current.querySelectorAll('td, th');
    for (const cell of cells) {
      if (cell.textContent?.toUpperCase().includes(OWNER_SIGNATURE_TITLE)) {
        cell.classList.add('doc-preview__sign-zone');
      }
    }
  }, [ready]);

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
        <span className="doc-preview__toolbar-zoom">{Math.round(zoom * 100)}%</span>
      </div>
      <div ref={canvasRef} className="doc-preview__canvas">
        {loading && <p className="eyebrow">Đang dựng bản xem trước…</p>}
        <div ref={pageRef} className="doc-preview__page" style={{ zoom }} />
      </div>
      <p style={{ fontSize: '0.6875rem', color: 'var(--ink-faint)', margin: 'var(--gap-3) 0 0' }}>
        Bản xem trước dựng từ chính file .docx; phông chữ có thể khác đôi chút tùy máy. Tải file để có bản in.
      </p>
    </div>
  );
}
