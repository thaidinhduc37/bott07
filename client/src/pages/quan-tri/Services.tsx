import { useCallback, useEffect, useState } from 'react';
import { adminApi, type ServiceStatus } from '@/services/admin-api';
import { PageHeader } from '@/components/shared/PageHeader';

function Light({ ok, label, detail }: { ok: boolean; label: string; detail?: string }) {
  return (
    <div className="spread" style={{ alignItems: 'baseline', gap: 'var(--gap-4)', padding: '0.6rem 0', borderBottom: '1px dotted var(--rule)' }}>
      <div>
        <div style={{ fontWeight: 500 }}>{label}</div>
        {detail && (
          <div style={{ fontSize: '0.75rem', color: 'var(--ink-faint)' }}>{detail}</div>
        )}
      </div>
      <span className={`tag ${ok ? 'tag--ok' : 'tag--seal'}`} style={{ flexShrink: 0 }}>
        {ok ? 'hoạt động' : 'không dùng được'}
      </span>
    </div>
  );
}

export default function ServicesPage() {
  const [s, setS] = useState<ServiceStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [at, setAt] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      setS(await adminApi.services());
      setAt(new Date());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    // Trạng thái dịch vụ là thứ người ta mở ra rồi để đó. 30 giây đủ nhanh để
    // thấy một dịch vụ chết, đủ chậm để không tự làm nặng thêm hệ thống đang ốm.
    const t = setInterval(() => void load(), 30_000);
    return () => clearInterval(t);
  }, [load]);

  if (loading) return <p className="eyebrow">Đang tải…</p>;

  return (
    <div className="stack">
      <PageHeader eyebrow="Vận hành" title="Trạng thái dịch vụ" />

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      {s && (
        <div className="page-grid">
          <div className="page-grid__main">
            <section className="sheet sheet--pad">
              <div className="spread" style={{ marginBottom: 'var(--gap-3)' }}>
                <h2 className="eyebrow" style={{ margin: 0 }}>
                  Phụ thuộc
                </h2>
                <span className={`tag ${s.status === 'ok' ? 'tag--ok' : 'tag--warn'}`}>
                  {s.status === 'ok' ? 'đủ dịch vụ' : 'thiếu dịch vụ'}
                </span>
              </div>

              <Light
                ok={s.dependencies.postgres.ok}
                label="PostgreSQL"
                detail={
                  s.dependencies.postgres.latencyMs !== null
                    ? `truy vấn thử mất ${s.dependencies.postgres.latencyMs} ms`
                    : 'không kết nối được'
                }
              />
              <Light
                ok={s.dependencies.ragService.ok}
                label="Dịch vụ RAG"
                detail={`${s.dependencies.ragService.url} — ${s.dependencies.ragService.detail}`}
              />
              <Light
                ok={Boolean(s.dependencies.llm?.ok)}
                label="LLM sinh câu trả lời"
                detail={
                  s.dependencies.llm?.ok
                    ? 'khóa API còn dùng được'
                    : (s.dependencies.llm?.detail ??
                      'chưa xác định — truy xuất và cổng từ chối vẫn hoạt động khi thiếu LLM')
                }
              />
            </section>

            {Object.keys(s.dependencies.ragService.collections).length > 0 && (
              <section className="sheet sheet--pad">
                <h2 className="eyebrow" style={{ marginBottom: 'var(--gap-4)' }}>
                  Chỉ mục tìm kiếm
                </h2>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                  <thead>
                    <tr style={{ textAlign: 'left', color: 'var(--ink-faint)' }}>
                      <th style={{ fontWeight: 400, padding: '0 0.6rem 0.3rem 0' }}>Bộ sưu tập</th>
                      <th style={{ fontWeight: 400, padding: '0 0.6rem 0.3rem' }}>Vector</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(s.dependencies.ragService.collections).map(([name, c]) => (
                      <tr key={name}>
                        <td className="mono" style={{ padding: '0.3rem 0.6rem 0.3rem 0' }}>{name}</td>
                        <td className="mono" style={{ padding: '0.3rem 0.6rem' }}>{c.dense_points}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}
          </div>

          <aside className="page-grid__aside">
            <section className="sheet sheet--pad">
              <div className="svc-refresh">
                <span className="svc-updated">
                  {at &&
                    `Cập nhật lúc ${new Intl.DateTimeFormat('vi-VN', {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                      hour12: false,
                    }).format(at)} · tự làm mới mỗi 30 giây`}
                </span>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => void load()}>
                  Làm mới ngay
                </button>
              </div>
              <h2 className="aside-h">Số liệu</h2>
              <dl className="svc-stats">
                <div className="svc-stats__row">
                  <dt>Tài khoản</dt>
                  <dd>{s.counters.users}</dd>
                </div>
                <div className="svc-stats__row">
                  <dt>Tài liệu đã lập chỉ mục</dt>
                  <dd>{s.counters.indexedDocumentVersions}</dd>
                </div>
                <div className="svc-stats__row">
                  <dt>Đơn đã lập</dt>
                  <dd>{s.counters.submissions}</dd>
                </div>
                <div className="svc-stats__row">
                  <dt>API chạy liên tục (phút)</dt>
                  <dd>{Math.floor(s.uptimeSeconds / 60)}</dd>
                </div>
                <div className="svc-stats__row">
                  <dt>Bộ nhớ tiến trình API (MB)</dt>
                  <dd>{s.memoryMb}</dd>
                </div>
              </dl>
              <p className="field__hint">
                API và pipeline RAG chạy chung một tiến trình Python, nên con số này gồm cả hai mô
                hình BGE-M3 và cross-encoder sau khi chúng được nạp ở câu hỏi đầu tiên. Bộ nhớ toàn
                máy (cả PostgreSQL, Chroma) đo riêng bằng{' '}
                <span className="mono">scripts/test/do-ram.ps1</span>.
              </p>
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}
