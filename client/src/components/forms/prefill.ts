import type { FieldValue, TableRowValue } from '@/services/forms-api';

/**
 * Điền sẵn đơn từ nơi khác trong ứng dụng (vd Kết quả học tập → "Xin học lại").
 *
 * Giá trị đi qua tham số `dien` của URL dưới dạng JSON. Chúng chỉ là GỢI Ý hiện sẵn trong ô nhập: người dùng
 * thấy và sửa được, rồi máy chủ vẫn kiểm tra lại như mọi đơn — không có đường nào để một liên kết ép dữ liệu
 * vào đơn mà người dùng không nhìn thấy. Khóa lạ bị `SubmissionForm` bỏ qua (nó chỉ đọc khóa của biểu mẫu).
 */
export function formPrefillUrl(templateCode: string, values: Record<string, FieldValue>): string {
  return `/sinh-vien/bieu-mau/${templateCode}?dien=${encodeURIComponent(JSON.stringify(values))}`;
}

const isRow = (r: unknown): r is TableRowValue =>
  typeof r === 'object' && r !== null && Object.values(r).every((v) => typeof v === 'string');

/** Đọc `dien` từ query string; trả `undefined` khi vắng hoặc hỏng. Chỉ nhận chuỗi và bảng các hàng chuỗi. */
export function parsePrefill(search: string): Record<string, FieldValue> | undefined {
  const raw = new URLSearchParams(search).get('dien');
  if (!raw) return undefined;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return undefined;
    const out: Record<string, FieldValue> = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (typeof value === 'string') out[key] = value.slice(0, 500);
      else if (Array.isArray(value) && value.every(isRow)) out[key] = value.slice(0, 30);
    }
    return Object.keys(out).length > 0 ? out : undefined;
  } catch {
    return undefined;
  }
}
