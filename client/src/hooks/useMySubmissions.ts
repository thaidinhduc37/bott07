import { useEffect, useState } from 'react';
import { formsApi, type SubmissionSummary } from '@/services/forms-api';

export function useMySubmissions() {
  const [items, setItems] = useState<SubmissionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    formsApi
      .list()
      .then((r) => setItems(r.items))
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  return { items, loading, error };
}
