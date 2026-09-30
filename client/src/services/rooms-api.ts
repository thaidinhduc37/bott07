import { api } from './api';

/**
 * Danh mục phòng học.
 *
 * Hợp đồng backend (agent F) — JSON camelCase, prefix `/rooms`. Mọi thao tác
 * ghi đều được audit phía server; phía client chỉ gọi và tải lại danh sách.
 */

/** Một phòng trong danh mục. */
export interface RoomItem {
  id: string;
  code: string;
  building: string | null;
  capacity: number | null;
  kind: string | null;
  note: string | null;
  isActive: boolean;
  /** Số buổi học + ca thi đang trỏ vào phòng này — 0 = chưa có lịch. */
  usageCount: number;
}

/** Một dòng trong lịch phòng: một buổi học hoặc một ca thi. */
export interface RoomTimetableItem {
  entryKind: 'SESSION' | 'EXAM';
  id: string;
  course: { code: string; name: string };
  class: { code: string };
  startsAt: string;
  endsAt: string;
}

/** Kết quả `GET /rooms/:id/timetable`. */
export interface RoomTimetable {
  room: RoomItem;
  from: string;
  to: string;
  items: RoomTimetableItem[];
}

/** Dữ liệu form phòng — dùng chung cho thêm và sửa. */
export interface RoomPayload {
  code: string;
  building?: string | null;
  capacity?: number | null;
  kind?: string | null;
  note?: string | null;
  /** Chỉ gửi khi sửa — thêm mới mặc định `true`. */
  isActive?: boolean;
}

export const roomsApi = {
  /** Danh sách phòng. `activeOnly` lọc phòng đang sử dụng; `search` khớp mã / tòa. */
  list: (params: { activeOnly?: boolean; search?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.activeOnly !== undefined) qs.set('activeOnly', String(params.activeOnly));
    if (params.search) qs.set('search', params.search);
    const s = qs.toString();
    return api<{ items: RoomItem[] }>(`/rooms${s ? `?${s}` : ''}`);
  },

  create: (data: RoomPayload) => api<RoomItem>('/rooms', { method: 'POST', body: data }),

  update: (id: string, data: Partial<RoomPayload>) =>
    api<RoomItem>(`/rooms/${id}`, { method: 'PATCH', body: data }),

  remove: (id: string) => api<{ message: string }>(`/rooms/${id}`, { method: 'DELETE' }),

  /** Lịch phòng trong khoảng ngày. Backend chặn khoảng > 62 ngày. */
  timetable: (id: string, from: string, to: string) => {
    const qs = new URLSearchParams({ from, to }).toString();
    return api<RoomTimetable>(`/rooms/${id}/timetable?${qs}`);
  },
};
