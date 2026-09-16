import { useCallback, useEffect, useRef, useState } from 'react';

const WIDTH = 520;
const HEIGHT = 200;

export interface SignaturePadProps {
  busy?: boolean;
  onSave: (png: Blob) => void;
}

/**
 * Ô vẽ chữ ký.
 *
 * Vẽ ở độ phân giải thật của màn hình (`devicePixelRatio`) rồi thu nhỏ bằng
 * CSS: chữ ký vẽ trên canvas 1× ở màn hình Retina trông như nét bút bị răng
 * cưa, và nét đó sẽ đi thẳng vào file đơn chính thức.
 *
 * Xuất PNG chứ không phải JPEG — chữ ký cần nền trong suốt để nằm trên giấy,
 * và JPEG không có kênh alpha.
 */
export function SignaturePad({ busy, onSave }: SignaturePadProps) {
  const [mode, setMode] = useState<'draw' | 'upload'>('draw');

  return (
    <div>
      <div className="seg" style={{ marginBottom: 'var(--gap-4)' }}>
        <label className={`seg__opt${mode === 'draw' ? ' seg__opt--on' : ''}`}>
          <input type="radio" name="sig-mode" checked={mode === 'draw'} onChange={() => setMode('draw')} />
          Vẽ bằng chuột
        </label>
        <label className={`seg__opt${mode === 'upload' ? ' seg__opt--on' : ''}`}>
          <input type="radio" name="sig-mode" checked={mode === 'upload'} onChange={() => setMode('upload')} />
          Tải ảnh PNG lên
        </label>
      </div>
      {mode === 'draw' ? <DrawPad busy={busy} onSave={onSave} /> : <UploadPad busy={busy} onSave={onSave} />}
    </div>
  );
}

/** Ảnh PNG có sẵn (quét từ giấy, xuất từ phần mềm ký...) — nét đều và sạch
 * hơn hẳn vẽ tay bằng chuột, chỉ cần nền trong suốt để chèn vào đơn giấy. */
function UploadPad({ busy, onSave }: SignaturePadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  function pick(f: File | null) {
    setError(null);
    if (!f) {
      setFile(null);
      setPreview(null);
      return;
    }
    if (f.type !== 'image/png') {
      setFile(null);
      setPreview(null);
      setError('Chỉ nhận file PNG (.png) — nền trong suốt để chèn được vào đơn giấy.');
      return;
    }
    setFile(f);
    setPreview(URL.createObjectURL(f));
  }

  return (
    <div>
      <label
        className="signature-pad"
        style={{
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: '1px dashed var(--rule)',
          maxWidth: `${WIDTH}px`,
          minHeight: `${HEIGHT}px`,
          cursor: 'pointer',
          background: preview ? '#fff' : 'var(--sheet-2)',
        }}
      >
        <input
          type="file"
          accept="image/png"
          style={{ position: 'absolute', width: 1, height: 1, opacity: 0 }}
          onChange={(e) => pick(e.target.files?.[0] ?? null)}
        />
        {preview ? (
          <img src={preview} alt="Xem trước chữ ký" style={{ maxWidth: '100%', maxHeight: HEIGHT, display: 'block' }} />
        ) : (
          <span style={{ color: 'var(--ink-soft)', fontSize: '0.875rem' }}>Bấm để chọn file PNG…</span>
        )}
      </label>

      {error && (
        <div className="notice notice--error" role="alert" style={{ marginTop: 'var(--gap-3)' }}>
          {error}
        </div>
      )}

      <div className="row" style={{ marginTop: 'var(--gap-4)' }}>
        <button type="button" className="btn btn--primary" onClick={() => file && onSave(file)} disabled={!file || busy}>
          {busy ? 'Đang lưu…' : 'Lưu chữ ký'}
        </button>
        {file && (
          <button type="button" className="btn btn--ghost" onClick={() => pick(null)} disabled={busy}>
            Chọn ảnh khác
          </button>
        )}
      </div>
      <p style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', margin: 'var(--gap-3) 0 0', maxWidth: 'var(--measure)' }}>
        Nên dùng ảnh nền trong suốt (PNG). Chữ ký này được chèn vào đơn khi bạn xác nhận bằng mã PIN
        ký — nó không tự động xuất hiện ở đâu cả.
      </p>
    </div>
  );
}

function DrawPad({ busy, onSave }: SignaturePadProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const dirty = useRef(false);
  const [hasInk, setHasInk] = useState(false);

  const setup = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = WIDTH * dpr;
    canvas.height = HEIGHT * dpr;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    // Đọc từ token thay vì ghi cứng. Nét ký được xuất thẳng ra PNG rồi chèn
    // vào đơn in trên giấy trắng, nên token này cố ý KHÔNG đổi theo chế độ tối
    // — xem ghi chú ở `--signature-ink` trong globals.css.
    ctx.strokeStyle =
      getComputedStyle(document.documentElement).getPropertyValue('--signature-ink').trim() ||
      '#12213a';
  }, []);

  useEffect(() => {
    setup();
  }, [setup]);

  function pointOf(e: React.PointerEvent<HTMLCanvasElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    // Toạ độ chuột theo pixel CSS của canvas đã co giãn; chia lại theo tỉ lệ
    // hiển thị để nét bút bám đúng đầu con trỏ trên mọi cỡ màn hình.
    return {
      x: ((e.clientX - rect.left) / rect.width) * WIDTH,
      y: ((e.clientY - rect.top) / rect.height) * HEIGHT,
    };
  }

  function start(e: React.PointerEvent<HTMLCanvasElement>) {
    const ctx = canvasRef.current?.getContext('2d');
    if (!ctx) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drawing.current = true;
    const p = pointOf(e);
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
  }

  function move(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawing.current) return;
    const ctx = canvasRef.current?.getContext('2d');
    if (!ctx) return;
    const p = pointOf(e);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    if (!dirty.current) {
      dirty.current = true;
      setHasInk(true);
    }
  }

  function end() {
    drawing.current = false;
  }

  function clear() {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    dirty.current = false;
    setHasInk(false);
  }

  function save() {
    const canvas = canvasRef.current;
    if (!canvas || !hasInk) return;
    canvas.toBlob((blob) => {
      if (blob) onSave(blob);
    }, 'image/png');
  }

  return (
    <div>
      <div
        className="signature-pad"
        style={{
          border: '1px solid var(--rule)',
          maxWidth: `${WIDTH}px`,
          position: 'relative',
        }}
      >
        <canvas
          ref={canvasRef}
          onPointerDown={start}
          onPointerMove={move}
          onPointerUp={end}
          onPointerLeave={end}
          style={{
            display: 'block',
            width: '100%',
            height: 'auto',
            aspectRatio: `${WIDTH} / ${HEIGHT}`,
            touchAction: 'none',
            cursor: 'crosshair',
          }}
        />
        {/* Dòng kẻ ký, vẽ bằng CSS nên không lọt vào ảnh xuất ra. */}
        <div
          aria-hidden="true"
          style={{
            position: 'absolute',
            left: '8%',
            right: '8%',
            bottom: '22%',
            borderBottom: '1px dotted var(--rule)',
            pointerEvents: 'none',
          }}
        />
      </div>

      <div className="row" style={{ marginTop: 'var(--gap-4)' }}>
        <button type="button" className="btn btn--primary" onClick={save} disabled={!hasInk || busy}>
          {busy ? 'Đang lưu…' : 'Lưu chữ ký'}
        </button>
        <button type="button" className="btn btn--ghost" onClick={clear} disabled={!hasInk || busy}>
          Vẽ lại
        </button>
      </div>
      <p style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', margin: 'var(--gap-3) 0 0', maxWidth: 'var(--measure)' }}>
        Dùng chuột, bút cảm ứng hoặc ngón tay. Chữ ký này được chèn vào đơn khi bạn xác nhận bằng mã
        PIN ký — nó không tự động xuất hiện ở đâu cả.
      </p>
    </div>
  );
}
