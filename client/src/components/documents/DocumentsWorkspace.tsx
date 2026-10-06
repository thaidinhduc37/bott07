import { useCallback, useEffect, useState } from 'react';
import { useSession } from '@/components/shared/SessionProvider';
import {
  DOCUMENT_TYPE_LABEL,
  INDEXABLE,
  documentsApi,
  type CourseRef,
  type DocumentItem,
  type DocumentType,
  type IndexStatusReport,
} from '@/services/documents-api';
import { PageHeader } from '@/components/shared/PageHeader';
import { DocumentRow } from './DocumentRow';
import { IndexHealth } from './IndexHealth';
import { UploadForm } from './UploadForm';

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
