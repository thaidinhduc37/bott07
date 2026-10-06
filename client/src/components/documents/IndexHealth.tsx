import { INDEX_STATUS_LABEL, type IndexStatus, type IndexStatusReport } from '@/services/documents-api';

export function IndexHealth({ report }: { report: IndexStatusReport }) {
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
