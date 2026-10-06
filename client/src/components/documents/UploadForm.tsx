import { useRef, useState } from 'react';
import { DOCUMENT_TYPE_LABEL, INDEXABLE, documentsApi, type CourseRef, type DocumentType } from '@/services/documents-api';

export function UploadForm({
  courses,
  isRagManager,
  onClose,
  onDone,
}: {
  courses: CourseRef[];
  isRagManager: boolean;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [title, setTitle] = useState('');
  const [documentType, setDocumentType] = useState<DocumentType>(isRagManager ? 'QUYCHE' : 'KHAC');
  const [courseId, setCourseId] = useState('');
  const [referenceNo, setReferenceNo] = useState('');
  const [issuedAt, setIssuedAt] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  const allowedTypes: DocumentType[] = isRagManager ? ['QUYCHE', 'GIAOTRINH', 'KHAC'] : ['KHAC'];
  const indexable = INDEXABLE.includes(documentType);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const doc = await documentsApi.upload(file, {
        title,
        documentType,
        courseId: courseId || undefined,
        referenceNo: referenceNo || undefined,
        issuedAt: issuedAt || undefined,
      });
      onDone(
        indexable
          ? `Đã nhận “${doc.title}”. Lập chỉ mục đang chạy nền — trạng thái tự cập nhật bên dưới.`
          : `Đã lưu “${doc.title}”.`,
      );
      formRef.current?.reset();
      setTitle('');
      setCourseId('');
      setReferenceNo('');
      setIssuedAt('');
      setFile(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form ref={formRef} className="sheet sheet--pad" onSubmit={submit}>
      <div className="spread" style={{ marginBottom: 'var(--gap-5)' }}>
        <h2 className="display" style={{ fontSize: '1.05rem', margin: 0 }}>
          Tài liệu mới
        </h2>
        <button type="button" className="btn btn--ghost" onClick={onClose}>
          Đóng
        </button>
      </div>

      <div className="field">
        <label className="field__label" htmlFor="doc-title">
          Tên tài liệu<span className="req">*</span>
        </label>
        <input
          id="doc-title"
          className="field__input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={300}
          required
        />
        <span className="field__hint">
          Tên này xuất hiện trong phần trích dẫn của mọi câu trả lời, nên hãy đặt đúng tên văn bản.
        </span>
      </div>

      <div className="field">
        <label className="field__label" htmlFor="doc-type">
          Loại<span className="req">*</span>
        </label>
        <select
          id="doc-type"
          className="field__input"
          value={documentType}
          onChange={(e) => setDocumentType(e.target.value as DocumentType)}
          style={{ maxWidth: '28rem' }}
        >
          {allowedTypes.map((t) => (
            <option key={t} value={t}>
              {DOCUMENT_TYPE_LABEL[t]}
            </option>
          ))}
        </select>
        <span className="field__hint">
          {indexable
            ? 'Tài liệu loại này đi vào chỉ mục tìm kiếm và có thể được trợ lý trích dẫn.'
            : 'Tài liệu giảng dạy được lưu trữ nhưng không đi vào chỉ mục — trợ lý không trích dẫn từ đây.'}
          {!isRagManager && ' Chỉ quản trị viên và cán bộ quản lý đào tạo được nạp nguồn cho trợ lý.'}
        </span>
      </div>

      {documentType === 'GIAOTRINH' && (
        <div className="field">
          <label className="field__label" htmlFor="doc-course">
            Môn học<span className="req">*</span>
          </label>
          <select
            id="doc-course"
            className="field__input"
            value={courseId}
            onChange={(e) => setCourseId(e.target.value)}
            required
            style={{ maxWidth: '28rem' }}
          >
            <option value="">— chọn môn —</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} — {c.name}
              </option>
            ))}
          </select>
          <span className="field__hint">
            Bắt buộc: khi sinh viên hỏi về một môn, hệ thống chỉ tìm trong giáo trình của môn đó.
          </span>
        </div>
      )}

      {documentType === 'QUYCHE' && (
        <div className="row" style={{ gap: 'var(--gap-4)', flexWrap: 'wrap' }}>
          <div className="field" style={{ flex: '1 1 14rem' }}>
            <label className="field__label" htmlFor="doc-ref">
              Số hiệu văn bản
            </label>
            <input
              id="doc-ref"
              className="field__input"
              value={referenceNo}
              onChange={(e) => setReferenceNo(e.target.value)}
              placeholder="123/QĐ-HVKTCNAN"
              maxLength={100}
            />
          </div>
          <div className="field" style={{ flex: '0 1 14rem' }}>
            <label className="field__label" htmlFor="doc-issued">
              Ngày ban hành
            </label>
            <input
              id="doc-issued"
              type="date"
              className="field__input"
              value={issuedAt}
              onChange={(e) => setIssuedAt(e.target.value)}
            />
          </div>
        </div>
      )}

      <div className="field">
        <label className="field__label" htmlFor="doc-file">
          Tệp<span className="req">*</span>
        </label>
        <input
          id="doc-file"
          type="file"
          className="field__input"
          accept=".pdf,.docx,.txt,.md"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          required
        />
        <span className="field__hint">
          PDF, DOCX hoặc văn bản thuần, tối đa 25 MB. Hệ thống kiểm tra nội dung thật của tệp chứ
          không tin phần đuôi tên.
        </span>
      </div>

      {error && (
        <div className="notice notice--error" role="alert" style={{ marginTop: 'var(--gap-4)' }}>
          {error}
        </div>
      )}

      <div className="row" style={{ marginTop: 'var(--gap-6)' }}>
        <button type="submit" className="btn btn--primary" disabled={busy || !file || !title}>
          {busy ? 'Đang tải lên…' : 'Tải lên'}
        </button>
      </div>
      {indexable && (
        <p style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', margin: 'var(--gap-3) 0 0' }}>
          Lập chỉ mục một giáo trình vài trăm trang có thể mất hàng chục phút. Bạn không cần mở trang
          này trong lúc chờ.
        </p>
      )}
    </form>
  );
}

// ---------------------------------------------------------------- một tài liệu
