import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '@/services/api';
import {
  formsApi,
  signaturesApi,
  type FieldValue,
  type SubmissionDetail,
  type VerifyResult,
} from '@/services/forms-api';

export function useSubmissionDetail(id: string) {
  const [s, setS] = useState<SubmissionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<string[]>([]);
  const [hasSignature, setHasSignature] = useState(false);
  const [signError, setSignError] = useState<string | null>(null);
  const [verification, setVerification] = useState<VerifyResult | null>(null);

  const load = useCallback(async () => {
    try {
      setS(await formsApi.get(id));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    signaturesApi
      .mine()
      .then((sig) => setHasSignature(Boolean(sig)))
      .catch(() => setHasSignature(false));
  }, []);

  async function sign(pin: string) {
    setBusy(true);
    setSignError(null);
    try {
      const updated = await formsApi.sign(id, pin);
      setS(updated);
      setFlash(`Đã ký ${updated.code}. Nội dung đơn giờ đã khóa.`);
    } catch (e) {
      setSignError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function submitForApproval() {
    setBusy(true);
    setError(null);
    try {
      const updated = await formsApi.submit(id);
      setS(updated);
      setFlash(`Đã gửi ${updated.code} tới ${updated.template.approvalFlow[0]?.title ?? 'cấp duyệt'}.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runVerify() {
    setBusy(true);
    try {
      setVerification(await formsApi.verify(id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function save(formData: Record<string, FieldValue>) {
    setBusy(true);
    setFieldErrors([]);
    try {
      setS(await formsApi.update(id, formData));
      setEditing(false);
      setFlash('Đã lưu. Bản in cũ đã bị xóa — bấm “Dựng bản in” để tạo lại theo nội dung mới.');
    } catch (e) {
      if (e instanceof ApiError) setFieldErrors(e.fieldErrors ?? [e.message]);
      else setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function render() {
    setBusy(true);
    setError(null);
    setFlash(null);
    try {
      const r = await formsApi.render(id);
      setFlash(`Đã dựng ${r.code}.docx (${(r.bytes / 1024).toFixed(0)} KB).`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  /** Trả `true` khi xóa thành công — nơi gọi (trang) tự điều hướng đi, hook
   * này không biết/không nên biết về routing. */
  async function remove(): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      await formsApi.remove(id);
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  return {
    s,
    loading,
    editing,
    setEditing,
    busy,
    error,
    flash,
    fieldErrors,
    hasSignature,
    signError,
    verification,
    sign,
    submitForApproval,
    runVerify,
    save,
    render,
    remove,
  };
}
