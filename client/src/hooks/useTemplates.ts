import { useEffect, useState } from 'react';
import { formsApi, type TemplateRef } from '@/services/forms-api';

export function useTemplates() {
  const [items, setItems] = useState<TemplateRef[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    formsApi
      .templates()
      .then((r) => setItems(r.items))
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  return {
    active: items.filter((t) => t.isActive),
    pending: items.filter((t) => !t.isActive),
    loading,
    error,
  };
}
