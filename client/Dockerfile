# =============================================================================
#  Web (Vite + React SPA) — dev (hot-reload) và production
#
#  Build production từ GỐC repo:
#      docker build -f client/Dockerfile --target production -t sa-web .
#  Build dev:
#      docker build -f client/Dockerfile --target dev -t sa-web-dev .
#
#  Vite build production ra một thư mục tĩnh (`dist/`); ảnh production chỉ cần
#  phục vụ nó qua HTTP với fallback về `index.html` cho mọi route (định tuyến
#  ở phía client).
# =============================================================================

FROM node:20-bookworm-slim AS base
WORKDIR /app

COPY package.json package-lock.json ./
COPY client/package.json client/
# `npm install`, KHÔNG phải `npm ci`.
#
# `lightningcss` (Tailwind v4) là addon nhị phân, mỗi nền tảng một gói optional
# riêng. `package-lock.json` được sinh trên Windows nên cây cài đặt trong đó
# chỉ ghi bản `win32-x64-msvc`. Trên linux, `npm ci` dựng lại đúng cây đó — tức
# là không có bản nhị phân nào dùng được — và build chết ở Tailwind với thông
# báo rất khó lần.
#
# Đây là lỗi đã biết của npm (npm/cli#4828), và cách khắc phục chính npm
# khuyến nghị là giải phụ thuộc lại từ đầu thay vì dựng lại cây trong lockfile.
#
# Phải XÓA lockfile trước: còn nó thì `npm install` vẫn dựng lại đúng cây cũ
# và bỏ qua gói optional của nền tảng hiện tại.
RUN rm -f package-lock.json && npm install --workspace client --include-workspace-root

# --------------------------------------------------------------------- dev
# Compose bind-mount `client/` (trừ `node_modules`, giữ bằng volume nặc danh)
# đè lên thư mục này — Vite HMR đọc thẳng code trên host.
FROM base AS dev
ENV NODE_ENV=development
WORKDIR /app/client
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# --------------------------------------------------------------------- build
FROM base AS build
COPY client/ client/

# VITE_* được nhúng vào bundle lúc build (đọc qua `import.meta.env`), không đọc
# lúc chạy. Vì vậy nó phải là build-arg; đặt vào `environment` của compose sẽ
# không có tác dụng gì.
ARG VITE_API_URL=http://localhost:4000/api
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build --workspace client

# --------------------------------------------------------------- production
FROM node:20-bookworm-slim AS production
WORKDIR /app

ENV NODE_ENV=production
ENV TZ=Asia/Ho_Chi_Minh
ENV PORT=3000

RUN npm install --global serve@14

COPY --from=build /app/client/dist ./dist

USER node
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/dang-nhap').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["serve", "-s", "dist", "-l", "3000"]
