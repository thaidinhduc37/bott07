import { useCallback, useEffect, useRef, useState } from 'react';
import { useSession } from '@/components/shared/SessionProvider';
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
import { PageHeader } from '@/components/shared/PageHeader';

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
  const [filterCourse, setFilterCourse] = useState('');
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

  // Lọc theo môn phía client: API không có tham số môn, và danh sách đã tải đủ.
  const visible = filterCourse ? items.filter((d) => d.course?.id === filterCourse) : items;

  // Cảnh báo lập chỉ mục lặp lại: cùng một nội dung chỉ hiện một lần ở đầu
  // danh sách, mỗi dòng chỉ còn một chấm nhỏ.
  const { commonWarning, commonCount } = groupWarnings(visible);
  const courseFilterable = items.some((d) => d.course);

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Nguồn tri thức"
        title="Quản lý tài liệu"
        description="Mọi câu trả lời của trợ lý đều phải trích dẫn được về một tài liệu ở đây."
      />

      <div className="page-grid">
        <div className="page-grid__main">
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

          {loading ? (
            <p className="eyebrow">Đang tải…</p>
          ) : visible.length === 0 ? (
            <div className="sheet sheet--pad">
              <p style={{ margin: 0, color: 'var(--ink-soft)' }}>
                {search || filterType || filterCourse
                  ? 'Không có tài liệu nào khớp bộ lọc.'
                  : 'Chưa có tài liệu nào. Bấm “Tải tài liệu lên” để bắt đầu.'}
              </p>
            </div>
          ) : (
            <>
              {commonWarning && (
                <div className="notice notice--warn">
                  {commonWarning}
                  {commonCount > 1 && (
                    <span style={{ display: 'block', marginTop: '0.25rem', fontSize: '0.8125rem' }}>
                      Áp dụng cho {commonCount} tài liệu.
                    </span>
                  )}
                </div>
              )}
              <div className="sheet doc-list">
                <p className="doc-list__count">
                  {visible.length} tài liệu
                  {filterCourse && visible.length !== total && ` (trong tổng số ${total})`}
                </p>
                <ul className="doc-list__items">
                  {visible.map((doc) => (
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
              </div>
            </>
          )}
        </div>

        <aside className="page-grid__aside">
          <button
            type="button"
            className="btn btn--primary btn--block"
            onClick={() => setUploadOpen((open) => !open)}
          >
            {uploadOpen ? 'Đóng biểu mẫu tải lên' : 'Tải tài liệu lên'}
          </button>

          {report && <IndexHealth report={report} />}

          <section className="sheet sheet--pad">
            <h2 className="aside-h">Lọc</h2>
            <div className="doc-filters">
              <label className="field">
                <span className="field__label">Tìm theo tên</span>
                <input
                  className="field__input"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Quy chế học tập…"
                />
              </label>
              <label className="field">
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
              {courseFilterable && (
                <label className="field">
                  <span className="field__label">Môn học</span>
                  <select
                    className="field__input"
                    value={filterCourse}
                    onChange={(e) => setFilterCourse(e.target.value)}
                  >
                    <option value="">Tất cả môn</option>
                    {courses.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.code} — {c.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

/**
 * Gom các cảnh báo lập chỉ mục cùng nội dung: nếu nhiều tài liệu dính cùng một
 * câu (vd thiếu GEMINI_API_KEY), chỉ hiện một lần ở đầu danh sách.
 */
function groupWarnings(items: DocumentItem[]): { commonWarning: string | null; commonCount: number } {
  const counts = new Map<string, number>();
  for (const d of items) {
    const w = d.latestVersion?.indexError;
    if (w) counts.set(w, (counts.get(w) ?? 0) + 1);
  }
  let best: string | null = null;
  let bestN = 0;
  for (const [w, n] of counts) {
    if (n > bestN) {
      best = w;
      bestN = n;
    }
  }
  return bestN >= 2 ? { commonWarning: best, commonCount: bestN } : { commonWarning: null, commonCount: 0 };
}

// --------------------------------------------------------------- sức khỏe chỉ mục

function IndexHealth({ report }: { report: IndexStatusReport }) {
  const inSync = report.consistency === 'in_sync';
  const rag = report.ragService;

  return (
    <section className="sheet sheet--pad">
      <div className="spread" style={{ marginBottom: 'var(--gap-3)' }}>
        <h2 className="aside-h" style={{ margin: 0 }}>
          Trạng thái chỉ mục
        </h2>
        <span className={`tag ${!rag.reachable ? 'tag--seal' : inSync ? 'tag--ok' : 'tag--warn'}`}>
          {!rag.reachable ? 'mất kết nối' : inSync ? 'khớp' : 'lệch'}
        </span>
      </div>

      {!rag.reachable ? (
        <div className="notice notice--error" style={{ fontSize: '0.8125rem' }}>
          Không gọi được dịch vụ RAG. Tài liệu vẫn tải lên được nhưng sẽ nằm ở trạng thái “chờ lập
          chỉ mục” cho tới khi dịch vụ trở lại.
        </div>
      ) : (
        !inSync && (
          <div className="notice notice--warn" style={{ fontSize: '0.8125rem' }}>
            {report.consistency === 'unknown'
              ? 'Chưa đối chiếu được PostgreSQL với Qdrant.'
              : report.consistency}
          </div>
        )
      )}

      <dl className="doc-idx">
        {(Object.keys(INDEX_STATUS_LABEL) as IndexStatus[]).map((s) => (
          <div key={s} className="doc-idx__row">
            <dt>{INDEX_STATUS_LABEL[s]}</dt>
            <dd>
              {report.postgres[s]?.versions ?? 0}
              {report.postgres[s]?.chunks ? (
                <span className="doc-idx__sub"> · {report.postgres[s]?.chunks} đoạn</span>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>

      {rag.reachable && (
        <div className="doc-idx__coll">
          <p className="field__hint" style={{ margin: 0 }}>
            Bộ sưu tập
          </p>
          <ul className="doc-idx__list">
            {Object.entries(rag.collections).map(([name, c]) => (
              <li key={name} className="doc-idx__item">
                <span className="mono doc-idx__name">{name}</span>
                <span className="mono doc-idx__nums">
                  {c.dense_points}
                  {c.sparse_documents !== undefined && ` · ${c.sparse_documents}`}
                </span>
                {c.in_sync !== undefined && (
                  <span className={`tag ${c.in_sync ? 'tag--ok' : 'tag--warn'}`}>
                    {c.in_sync ? 'khớp' : 'lệch'}
                  </span>
                )}
              </li>
            ))}
          </ul>
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
  const warning = v?.indexError ?? null;

  return (
    <li className="doc-row">
      <div className="doc-row__top">
        <h3 className="doc-row__title">{doc.title}</h3>
        <span
          className={`tag ${indexable ? STATUS_TAG[status] : 'tag--muted'}`}
          style={{ flexShrink: 0 }}
        >
          {indexable ? INDEX_STATUS_LABEL[status] : 'ngoài chỉ mục'}
        </span>
      </div>
      <div className="doc-row__bottom">
        <p className="doc-row__meta">
          {DOCUMENT_TYPE_LABEL[doc.documentType]}
          {doc.course && ` · ${doc.course.code} ${doc.course.name}`}
          {v && (
            <>
              {' · '}
              <span className="mono">{v.fileName}</span> · {formatBytes(v.fileSize)} · bản {v.version}
            </>
          )}
          {' · '}
          {doc.uploadedBy.fullName} · {formatDate(doc.createdAt)}
          {warning && (
            <span className="doc-row__warn" title={warning} aria-label={`Cảnh báo: ${warning}`}>
              <span className="doc-row__warn-dot" aria-hidden="true" />
              có cảnh báo
            </span>
          )}
        </p>
        {canManage && (
          <span className="doc-row__actions">
            {indexable && (
              <button
                type="button"
                className="btn btn--quiet btn--sm"
                onClick={onReindex}
                disabled={status === 'PROCESSING'}
              >
                {status === 'FAILED' ? 'Thử lập chỉ mục lại' : 'Lập lại chỉ mục'}
              </button>
            )}
            {confirming ? (
              <>
                <button type="button" className="btn btn--danger btn--sm" onClick={onRemove}>
                  Xóa hẳn
                </button>
                <button type="button" className="btn btn--quiet btn--sm" onClick={() => setConfirming(false)}>
                  Thôi
                </button>
                <span className="doc-row__confirm-hint">
                  Xóa cả tệp lẫn vector. Không hoàn tác được.
                </span>
              </>
            ) : (
              <button type="button" className="btn btn--quiet btn--sm" onClick={() => setConfirming(true)}>
                Xóa
              </button>
            )}
          </span>
        )}
      </div>
    </li>
  );
}
