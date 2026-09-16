import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    // Bind-mount qua Docker Desktop trên Windows không truyền sự kiện
    // filesystem gốc đáng tin cậy cho container Linux — chuyển sang polling
    // trong trường hợp đó. Chỉ bật khi chạy trong container dev (biến
    // VITE_USE_POLLING do docker-compose.dev.yml đặt); `npm run dev` chạy
    // thẳng trên host vẫn dùng watcher gốc, không tốn CPU polling.
    watch: {
      usePolling: process.env.VITE_USE_POLLING === '1',
    },
  },
});
