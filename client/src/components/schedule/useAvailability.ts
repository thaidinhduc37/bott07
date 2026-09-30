import { useEffect, useRef, useState } from 'react';
import { scheduleApi, type Availability } from '@/services/schedule-api';

/**
 * Hỏi `GET /schedules/availability` khi ngày/giờ đổi, debounce 400ms để không
 * bắn request mỗi lần gõ. Trả về `rooms` (gợi ý phòng rảnh) và `lecturers`
 * (cảnh báo giảng viên bận). `excludeId` là buổi/ca đang sửa — để không tự
 * cảnh báo trùng chính nó.
 */
export function useAvailability(
  date: string,
  startTime: string,
  endTime: string,
  excludeId?: string,
) {
  const [data, setData] = useState<Availability | null>(null);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);

  useEffect(() => {
    // Cần đủ ngày + cả hai giờ mới hỏi được.
    if (!date || !startTime || !endTime) {
      setData(null);
      setLoading(false);
      return;
    }
    const id = ++seq.current;
    const t = window.setTimeout(() => {
      setLoading(true);
      scheduleApi
        .availability({ date, startTime, endTime, excludeId })
        .then((r) => {
          if (seq.current === id) setData(r);
        })
        .catch(() => {
          // Không chặn lưu khi không lấy được gợi ý — chỉ bỏ gợi ý.
          if (seq.current === id) setData(null);
        })
        .finally(() => {
          if (seq.current === id) setLoading(false);
        });
    }, 400);
    return () => window.clearTimeout(t);
  }, [date, startTime, endTime, excludeId]);

  return { data, loading };
}
