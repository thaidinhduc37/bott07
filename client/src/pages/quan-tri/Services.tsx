import { useCallback, useEffect, useState } from 'react';
import { adminApi, type ServiceStatus } from '@/services/admin-api';
import { StatTile } from '@/components/shared/StatTile';

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
      <header className="spread" style={{ alignItems: 'flex-end', gap: 'var(--gap-4)' }}>
        <div>
          <span className="eyebrow">Vận hành</span>
          <h1 className="display page-title">
            Trạng thái dịch vụ
          </h1>
          {at && (
            <p style={{ margin: '0.35rem 0 0', fontSize: '0.75rem', color: 'var(--ink-faint)' }}>
              Cập nhật lúc{' '}
              {new Intl.DateTimeFormat('vi-VN', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false,
              }).format(at)}{' '}
              · tự làm mới mỗi 30 giây
            </p>
          )}
        </div>
        <button type="button" className="btn btn--ghost" style={{ flexShrink: 0 }} onClick={() => void load()}>
          Làm mới ngay
        </button>
      </header>

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      )}

      {s && (
        <>
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
                    <th style={{ fontWeight: 400, padding: '0 0.6rem 0.3rem' }}>BM25</th>
                    <th style={{ fontWeight: 400, padding: '0 0 0.3rem' }}>Đồng bộ</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(s.dependencies.ragService.collections).map(([name, c]) => (
                    <tr key={name}>
                      <td className="mono" style={{ padding: '0.3rem 0.6rem 0.3rem 0' }}>{name}</td>
                      <td className="mono" style={{ padding: '0.3rem 0.6rem' }}>{c.dense_points}</td>
                      <td className="mono" style={{ padding: '0.3rem 0.6rem' }}>{c.sparse_documents}</td>
                      <td style={{ padding: '0.3rem 0' }}>
                        <span className={`tag ${c.in_sync ? 'tag--ok' : 'tag--warn'}`}>
                          {c.in_sync ? 'khớp' : 'lệch'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          <section className="sheet sheet--pad">
            <h2 className="eyebrow" style={{ marginBottom: 'var(--gap-4)' }}>
              Số liệu
            </h2>
            <div className="row" style={{ gap: 'var(--gap-6)' }}>
              <StatTile value={s.counters.users} label="Tài khoản" tone="pen" />
              <StatTile value={s.counters.indexedDocumentVersions} label="Tài liệu đã lập chỉ mục" tone="pen" />
              <StatTile value={s.counters.submissions} label="Đơn đã lập" tone="pen" />
              <StatTile value={Math.floor(s.uptimeSeconds / 60)} label="API chạy liên tục (phút)" tone="pen" />
              <StatTile value={s.memoryMb} label="Bộ nhớ tiến trình API (MB)" tone="pen" />
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--ink-faint)', margin: 'var(--gap-4) 0 0', maxWidth: 'var(--measure)' }}>
              “Bộ nhớ tiến trình API” chỉ là phần của Node.js. Hai mô hình nặng (BGE-M3 và
              cross-encoder) nằm trong tiến trình Python của dịch vụ RAG nên không tính ở đây — con
              số toàn máy được đo riêng bằng <span className="mono">scripts/test/do-ram.ps1</span>.
            </p>
          </section>
        </>
      )}
    </div>
  );
}
