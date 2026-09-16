import { useEffect, useState } from 'react';
import { ApiError } from '@/services/api';
import { formsApi, type FieldValue, type TemplateDetail } from '@/services/forms-api';

/**
 * `onCreated` thay vì tự `navigate()` — trang độc lập và modal "Tạo đơn mới"
 * ở trang "Đơn của tôi" cần đi tiếp khác nhau sau khi tạo xong (đổi route so
 * với chỉ đổi query param của modal), nên nơi gọi tự quyết định.
 */
export function useNewSubmission(code: string, onCreated: (id: string) => void) {
  const [tpl, setTpl] = useState<TemplateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<string[]>([]);

  useEffect(() => {
    formsApi
      .template(code)
      .then(setTpl)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [code]);

  async function submit(formData: Record<string, FieldValue>) {
    setBusy(true);
    setError(null);
    setFieldErrors([]);
    try {
      const created = await formsApi.create(code, formData);
      onCreated(created.id);
    } catch (e) {
      if (e instanceof ApiError) {
        setFieldErrors(e.fieldErrors ?? [e.message]);
      } else {
        setError((e as Error).message);
      }
      setBusy(false);
    }
  }

  return { tpl, loading, busy, error, fieldErrors, submit, cancelHref: '/sinh-vien/bieu-mau' as const };
}
