import type { IndexStatus } from '@/services/documents-api';
import { useState } from 'react';
import { DOCUMENT_TYPE_LABEL, INDEXABLE, INDEX_STATUS_LABEL, formatBytes, formatDate, type DocumentItem } from '@/services/documents-api';

const STATUS_TAG: Record<IndexStatus, string> = {
  UPLOADED: 'tag--muted',
  PROCESSING: 'tag--warn',
  INDEXED: 'tag--ok',
  FAILED: 'tag--seal',
};

export function DocumentRow({
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
