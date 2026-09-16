import { useCallback, useEffect, useRef, useState } from 'react';
import { useSession } from '@/components/shared/SessionProvider';
import { Icon } from '@/components/shared/Icon';
import {
  DOCUMENT_TYPE_LABEL,
  INDEXABLE,
  INDEX_STATUS_LABEL,
  documentsApi,
  formatBytes,
  formatDate,
  type CourseRef,
  type DocumentItem,
  type DocumentType,
  type IndexStatus,
  type IndexStatusReport,
} from '@/services/documents-api';

const STATUS_TAG: Record<IndexStatus, string> = {
  UPLOADED: 'tag--muted',
  PROCESSING: 'tag--warn',
  INDEXED: 'tag--ok',
  FAILED: 'tag--seal',
};

/**
 * Màn hình quản lý nguồn tài liệu.
 *
 * Dùng chung cho `/quan-tri/tai-lieu` và `/can-bo/tai-lieu`: cùng một API, cùng
 * một quyền hạn ở phía máy chủ. Khác biệt duy nhất giữa hai vai trò là loại tài
 * liệu được phép nạp, và điều đó được suy ra từ phiên đăng nhập chứ không phải
 * từ đường dẫn — hai trang khác nhau chỉ để menu điều hướng đúng chỗ.
 */
export function DocumentsWorkspace() {
  const { user } = useSession();
  const roles = user?.roles ?? [];
  const isRagManager = roles.includes('ADMIN') || roles.includes('ACADEMIC_MANAGER');

  const [items, setItems] = useState<DocumentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [courses, setCourses] = useState<CourseRef[]>([]);
  const [report, setReport] = useState<IndexStatusReport | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [filterType, setFilterType] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  /**
   * `quiet` dùng cho các lần hỏi lại tự động.
   *
   * Một lần hỏi nền trượt không phải là chuyện người dùng cần biết: dữ liệu cũ
   * vẫn đúng và lần sau sẽ lấy lại được. Dựng banner lỗi cho nó chỉ dạy người
   * dùng bỏ qua banner lỗi.
   */
  const load = useCallback(
    async (quiet = false) => {
      try {
        const [list, status] = await Promise.all([
          documentsApi.list({ documentType: filterType || undefined, search: search || undefined }),
          documentsApi.indexStatus().catch(() => null),
        ]);
        setItems(list.items);
        setTotal(list.total);
        if (status) setReport(status);
        setError(null);
      } catch (e) {
        if (!quiet) setError((e as Error).message || 'Không tải được danh sách tài liệu');
      } finally {
        setLoading(false);
      }
    },
    [filterType, search],
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void documentsApi.courses().then((r) => setCourses(r.items)).catch(() => setCourses([]));
  }, []);

  /**
   * Lập chỉ mục chạy nền ở máy chủ, nên trạng thái trên màn hình sẽ cũ dần.
   *
   * Chỉ hỏi lại khi thực sự có tài liệu đang xử lý — không polling vô cớ. Nhịp
   * 10 giây được chọn theo thời gian thật của công việc: nạp một tài liệu mất
   * hàng chục giây tới hàng chục phút, nên hỏi mỗi 2-3 giây không cho biết thêm
   * gì mà chỉ đốt hạn mức 120 request/phút của API — và khi đã cạn hạn mức thì
   * chính màn hình này ngừng cập nhật.
   */
  const processing = items.some((d) => d.latestVersion?.indexStatus === 'PROCESSING');
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(() => void load(true), 10_000);
    return () => clearInterval(t);
  }, [processing, load]);

  async function act(fn: () => Promise<{ message: string }>) {
    setError(null);
    // Xóa thông báo cũ trước: một dòng "đã xóa xong" nằm cạnh một lỗi mới khiến
    // người dùng không biết dòng nào nói về thao tác vừa rồi.
    setFlash(null);
    try {
      const r = await fn();
      setFlash(r.message);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="stack">
      <header className="spread" style={{ alignItems: 'flex-end', gap: 'var(--gap-4)' }}>
        <div>
          <span className="eyebrow">Nguồn tri thức</span>
          <h1
            className="display"
            style={{ fontSize: 'clamp(1.4rem, 1.15rem + 1vw, 1.85rem)', margin: '0.25rem 0 0' }}
          >
            Quản lý tài liệu
          </h1>
          <p className="page-sub">
            Mọi câu trả lời của trợ lý đều phải trích dẫn được về một tài liệu ở đây. Tài liệu chưa
            lập chỉ mục xong thì chưa có mặt trong câu trả lời nào — trạng thái bên dưới nói rõ từng
            tệp đang ở bước nào.
          </p>
        </div>
        {!uploadOpen && (
          <button
            type="button"
            className="btn btn--primary"
            style={{ flexShrink: 0 }}
            onClick={() => setUploadOpen(true)}
          >
            Tải tài liệu lên
          </button>
        )}
      </header>

      {uploadOpen && (
        <UploadForm
          courses={courses}
          isRagManager={isRagManager}
          onClose={() => setUploadOpen(false)}
          onDone={(msg) => {
            setFlash(msg);
            setUploadOpen(false);
            void load();
          }}
        />
      )}

      {report && <IndexHealth report={report} />}

      {flash && (
        <div className="notice notice--ok" role="status">
          {flash}
        </div>
      )}
      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      {/* ------------------------------------------------------------ bộ lọc */}
      <div className="sheet" style={{ padding: '0.85rem 1.1rem' }}>
        <div className="row" style={{ gap: 'var(--gap-4)', flexWrap: 'wrap' }}>
          <label style={{ flex: '1 1 14rem' }}>
            <span className="field__label">Tìm theo tên</span>
            <input
              className="field__input"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Quy chế học tập…"
            />
          </label>
          <label style={{ flex: '0 1 16rem' }}>
            <span className="field__label">Loại tài liệu</span>
            <select
              className="field__input"
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
            >
              <option value="">Tất cả loại</option>
              {(Object.keys(DOCUMENT_TYPE_LABEL) as DocumentType[]).map((t) => (
                <option key={t} value={t}>
                  {DOCUMENT_TYPE_LABEL[t]}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {/* ---------------------------------------------------------- danh sách */}
      {loading ? (
        <p className="eyebrow">Đang tải…</p>
      ) : items.length === 0 ? (
        <div className="sheet sheet--pad">
          <p style={{ margin: 0, color: 'var(--ink-soft)' }}>
            {search || filterType
              ? 'Không có tài liệu nào khớp bộ lọc.'
              : 'Chưa có tài liệu nào. Tải tệp đầu tiên lên bằng biểu mẫu phía trên.'}
          </p>
        </div>
      ) : (
        <>
          <p className="eyebrow" style={{ margin: 0 }}>
            {total} tài liệu
          </p>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: '1px', background: 'var(--rule-faint)', border: '1px solid var(--rule-faint)' }}>
            {items.map((doc) => (
              <DocumentRow
                key={doc.id}
                doc={doc}
                canManage={isRagManager || !INDEXABLE.includes(doc.documentType)}
                onReindex={() => act(() => documentsApi.reindex(doc.id))}
                onRemove={() =>
                  act(async () => {
                    const r = await documentsApi.remove(doc.id);
                    return {
                      message: `${r.message} — xóa ${r.vectorsRemoved} vector, ${r.filesRemoved} tệp.`,
                    };
                  })
                }
              />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

// --------------------------------------------------------------- sức khỏe chỉ mục

function IndexHealth({ report }: { report: IndexStatusReport }) {
  const inSync = report.consistency === 'in_sync';
  const rag = report.ragService;

  return (
    <section className="sheet sheet--pad">
      <div className="spread" style={{ marginBottom: 'var(--gap-4)' }}>
        <h2 className="display" style={{ fontSize: '1.05rem', margin: 0 }}>
          Trạng thái chỉ mục
        </h2>
        <span className={`tag ${!rag.reachable ? 'tag--seal' : inSync ? 'tag--ok' : 'tag--warn'}`}>
          {!rag.reachable ? 'mất kết nối' : inSync ? 'khớp' : 'lệch'}
        </span>
      </div>

      {!rag.reachable ? (
        <div className="notice notice--error">
          Không gọi được dịch vụ RAG. Tài liệu vẫn tải lên được nhưng sẽ nằm ở trạng thái “chờ lập
          chỉ mục” cho tới khi dịch vụ trở lại.
        </div>
      ) : (
        !inSync && (
          <div className="notice notice--warn">
            {report.consistency === 'unknown'
              ? 'Chưa đối chiếu được PostgreSQL với Qdrant.'
              : report.consistency}
          </div>
        )
      )}

      <dl
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(9rem, 1fr))',
          gap: 'var(--gap-4)',
          margin: 'var(--gap-5) 0 0',
        }}
      >
        {(Object.keys(INDEX_STATUS_LABEL) as IndexStatus[]).map((s) => (
          <div key={s}>
            <dt className="eyebrow">{INDEX_STATUS_LABEL[s]}</dt>
            <dd className="mono" style={{ margin: '0.15rem 0 0', fontSize: '0.9375rem' }}>
              {report.postgres[s]?.versions ?? 0}
              {report.postgres[s]?.chunks ? (
                <span style={{ color: 'var(--ink-faint)' }}> · {report.postgres[s]?.chunks} đoạn</span>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>

      {rag.reachable && (
        <div style={{ marginTop: 'var(--gap-5)', borderTop: '1px dotted var(--rule)', paddingTop: 'var(--gap-4)' }}>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Bộ sưu tập</th>
                  {/* Hai cột này là số đếm được đặt cạnh nhau để so — căn phải
                      và dùng chữ đẳng khoảng thì chỗ lệch đập vào mắt ngay. */}
                  <th className="num">Vector</th>
                  <th className="num">BM25</th>
                  <th>Đồng bộ</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(rag.collections).map(([name, c]) => (
                  <tr key={name}>
                    <td className="mono">{name}</td>
                    <td className="mono num">{c.dense_points}</td>
                    <td className="mono num">{c.sparse_documents}</td>
                    <td>
                      <span className={`tag ${c.in_sync ? 'tag--ok' : 'tag--warn'}`}>
                        {c.in_sync ? 'khớp' : 'lệch'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!rag.llm.ok && (
            <p style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', margin: 'var(--gap-3) 0 0' }}>
              {/* Dịch vụ RAG đã nói rõ hỏng gì và hệ quả ra sao. Nhắc lại ở đây
                  chỉ làm loãng câu, nên chỉ đặt nhãn rồi dẫn nguyên văn. */}
              LLM chưa dùng được
              {rag.llm.detail ? ` — ${rag.llm.detail}` : '.'}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

// ------------------------------------------------------------------- tải lên

function UploadForm({
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

function DocumentRow({
  doc,
  canManage,
  onReindex,
  onRemove,
}: {
  doc: DocumentItem;
  canManage: boolean;
  onReindex: () => void;
  onRemove: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const v = doc.latestVersion;
  const status = v?.indexStatus ?? 'UPLOADED';
  const indexable = INDEXABLE.includes(doc.documentType);

  return (
    <li style={{ background: 'var(--sheet)', padding: '1rem 1.15rem' }}>
      <div className="spread" style={{ alignItems: 'flex-start', gap: 'var(--gap-4)' }}>
        {/* Biểu tượng loại tài liệu ở đầu dòng: danh sách này được quét theo
            chiều dọc, và một mỏ neo thị giác cố định giúp mắt bắt đầu dòng
            nhanh hơn là phải đọc chữ đầu tiên của tiêu đề. */}
        <div style={{ minWidth: 0, display: 'grid', gridTemplateColumns: '1.125rem minmax(0, 1fr)', gap: 'var(--gap-3)' }}>
          <Icon
            name={doc.documentType === 'GIAOTRINH' ? 'book' : 'log'}
            size={18}
            style={{ marginTop: '0.2rem', color: 'var(--ink-faint)' }}
          />
          <div style={{ minWidth: 0 }}>
          <h3 className="display" style={{ fontSize: '1rem', margin: 0 }}>
            {doc.title}
          </h3>
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.8125rem', color: 'var(--ink-soft)' }}>
            {DOCUMENT_TYPE_LABEL[doc.documentType]}
            {doc.course && ` · ${doc.course.code} ${doc.course.name}`}
            {doc.referenceNo && ` · số ${doc.referenceNo}`}
            {doc.issuedAt && ` · ban hành ${formatDate(doc.issuedAt)}`}
          </p>
          <p style={{ margin: '0.15rem 0 0', fontSize: '0.75rem', color: 'var(--ink-faint)' }}>
            {v && (
              <>
                <span className="mono">{v.fileName}</span> · {formatBytes(v.fileSize)} · bản {v.version} ·{' '}
              </>
            )}
            {doc.uploadedBy.fullName} tải lên {formatDate(doc.createdAt)}
          </p>
          </div>
        </div>
        <span className={`tag ${indexable ? STATUS_TAG[status] : 'tag--muted'}`} style={{ flexShrink: 0 }}>
          {indexable ? INDEX_STATUS_LABEL[status] : 'ngoài chỉ mục'}
        </span>
      </div>

      {indexable && status === 'INDEXED' && v && (
        <p style={{ margin: '0.5rem 0 0', fontSize: '0.75rem', color: 'var(--ink-faint)' }}>
          {v.pageCount ?? '—'} trang → {v.chunkCount ?? 0} đoạn
          {v.contextualCount ? `, ${v.contextualCount} có ngữ cảnh LLM` : ''}
          {v.indexedAt && ` · xong ${formatDate(v.indexedAt)}`}
          {v.indexError && (
            <>
              {' · '}
              <span style={{ color: 'var(--seal)' }}>cảnh báo: {v.indexError}</span>
            </>
          )}
        </p>
      )}

      {indexable && status === 'FAILED' && v?.indexError && (
        <div className="notice notice--error" style={{ marginTop: 'var(--gap-3)', fontSize: '0.8125rem' }}>
          {v.indexError}
        </div>
      )}

      {canManage && (
        <div className="row" style={{ marginTop: 'var(--gap-4)', gap: 'var(--gap-3)' }}>
          {indexable && (
            <button
              type="button"
              className="btn btn--ghost"
              onClick={onReindex}
              disabled={status === 'PROCESSING'}
            >
              {status === 'FAILED' ? 'Thử lập chỉ mục lại' : 'Lập lại chỉ mục'}
            </button>
          )}
          {confirming ? (
            <>
              <button type="button" className="btn btn--danger" onClick={onRemove}>
                Xóa hẳn
              </button>
              <button type="button" className="btn btn--ghost" onClick={() => setConfirming(false)}>
                Thôi
              </button>
              <span style={{ fontSize: '0.75rem', color: 'var(--ink-faint)' }}>
                Xóa cả tệp lẫn vector. Không hoàn tác được.
              </span>
            </>
          ) : (
            <button type="button" className="btn btn--ghost" onClick={() => setConfirming(true)}>
              Xóa
            </button>
          )}
        </div>
      )}
    </li>
  );
}
