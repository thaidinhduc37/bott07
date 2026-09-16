import type { StatusBarItem } from '@/components/shared/charts/StatusBarList';

export const STATUS_LABEL: Record<string, string> = {
  DRAFT: 'Nháp',
  SUBMITTED: 'Đã gửi',
  UNDER_REVIEW: 'Đang xét duyệt',
  NEEDS_REVISION: 'Cần bổ sung',
  REJECTED: 'Bị từ chối',
  APPROVED: 'Đã duyệt',
  COMPLETED: 'Hoàn tất',
};

export const INDEX_STATUS_LABEL: Record<string, string> = {
  UPLOADED: 'Mới tải lên',
  PROCESSING: 'Đang xử lý',
  INDEXED: 'Đã lập chỉ mục',
  FAILED: 'Lỗi',
};

/** Màu ngữ nghĩa dùng chung cho mọi mã trạng thái trong dashboard — đơn từ
 *  lẫn tài liệu đều dùng "REJECTED/FAILED = đỏ, đã xong = lục". */
export function toneFor(code: string): StatusBarItem['tone'] {
  if (code === 'REJECTED' || code === 'FAILED') return 'seal';
  if (code === 'NEEDS_REVISION') return 'warn';
  if (code === 'APPROVED' || code === 'COMPLETED' || code === 'INDEXED') return 'ok';
  if (code === 'DRAFT' || code === 'UPLOADED') return 'muted';
  return 'pen';
}

/** Tỉ lệ 0-1 (hoặc null khi chưa có mẫu) thành phần trăm nguyên để hiện lên
 *  `StatTile` — `StatTile.value` chỉ nhận `number`, không nhận `null`. */
export function pct(rate: number | null): number {
  return rate === null ? 0 : Math.round(rate * 100);
}
