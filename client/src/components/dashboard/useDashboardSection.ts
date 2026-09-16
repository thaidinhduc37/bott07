import { useEffect, useState } from 'react';

export type Loaded<T> =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ok'; data: T };

/**
 * Tải dữ liệu một khối dashboard, độc lập với các khối khác — lỗi ở đây
 * không lan sang khối khác vì mỗi khối gọi hook này riêng, không có
 * `Promise.all` chung nào bọc ngoài.
 */
export function useDashboardSection<T>(fetcher: () => Promise<T>, refreshKey: number): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    fetcher()
      .then((data) => {
        if (!cancelled) setState({ status: 'ok', data });
      })
      .catch((e) => {
        if (!cancelled) setState({ status: 'error', message: (e as Error).message });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  return state;
}
