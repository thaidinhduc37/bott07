import { useEffect } from 'react';

const SUFFIX = 'Trợ lý ảo hỗ trợ học viên';

export function useDocumentTitle(title?: string) {
  useEffect(() => {
    document.title = title ? `${title} · ${SUFFIX}` : SUFFIX;
  }, [title]);
}
