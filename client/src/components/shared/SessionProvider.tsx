import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, authApi, type MeResponse } from '@/services/api';

interface SessionValue {
  user: MeResponse | null;
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
  logout: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const [user, setUser] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setUser(await authApi.me());
      setError(null);
    } catch (e) {
      setUser(null);
      if (e instanceof ApiError && e.status === 401) {
        // Cookie còn nhưng phiên đã hết — middleware không phát hiện được điều
        // này vì nó chỉ nhìn thấy cookie có tồn tại hay không.
        navigate('/dang-nhap', { replace: true });
      } else {
        setError(
          e instanceof ApiError
            ? e.message
            : 'Không kết nối được tới máy chủ. Kiểm tra xem dịch vụ API đã chạy chưa.',
        );
      }
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setUser(null);
      navigate('/dang-nhap', { replace: true });
    }
  }, [navigate]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <SessionContext.Provider value={{ user, loading, error, reload, logout }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession phải nằm trong <SessionProvider>');
  return ctx;
}
