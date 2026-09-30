import type { Readiness } from '@/services/learning-api';

// Điểm dạng Việt: dấu phẩy thập phân ("6,0" thay vì "6.0").
export const viScore = (n: number) => n.toFixed(1).replace('.', ',');

export const MONTHS = ['Th1', 'Th2', 'Th3', 'Th4', 'Th5', 'Th6', 'Th7', 'Th8', 'Th9', 'Th10', 'Th11', 'Th12'];
const WEEKDAY = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'];

/** "T3, 02/12". Tự định dạng vì Intl vi-VN cho "Thứ 3, 02-12" — dài và dùng gạch ngang. */
export function dayLabel(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  return `${WEEKDAY[date.getDay()]}, ${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}`;
}

export function rangeLabel(from: string, to: string): string {
  return from === to ? dayLabel(from) : `${dayLabel(from)} – ${dayLabel(to)}`;
}

export const READINESS_TAG: Record<Readiness, { cls: string; label: string }> = {
  CHUA_ON: { cls: 'tag--muted', label: 'Chưa ôn' },
  CAN_ON_THEM: { cls: 'tag--warn', label: 'Cần ôn thêm' },
  ON_DINH: { cls: 'tag--ok', label: 'Ổn định' },
};
