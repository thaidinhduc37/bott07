import { useCallback, useState } from 'react';

const STORAGE_KEY = 'theme';

/** Trạng thái hiện đang hiển thị, bất kể do OS hay do người dùng tự chọn. */
function computeIsDark(): boolean {
  const explicit = document.documentElement.getAttribute('data-theme');
  if (explicit === 'dark') return true;
  if (explicit === 'light') return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

/**
 * Bật/tắt giao diện sáng-tối thủ công. Mặc định theo hệ điều hành: `data-theme` chỉ xuất hiện trên `<html>` sau khi người dùng chọn
 * tay (script trong `index.html` đặt sẵn trước khi React mount để không nháy sai màu). Bấm nút luôn thành lựa chọn tường minh.
 */
export function useTheme() {
  const [isDark, setIsDark] = useState(computeIsDark);

  const toggle = useCallback(() => {
    setIsDark((current) => {
      const next = !current;
      const theme = next ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', theme);
      localStorage.setItem(STORAGE_KEY, theme);
      return next;
    });
  }, []);

  return { isDark, toggle };
}
