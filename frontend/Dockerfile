# === VideoNote 前端构建 ===
# Node 20 + pnpm → nginx 静态服务

ARG BASE_REGISTRY=docker.io

# ---------- 构建阶段 ----------
FROM ${BASE_REGISTRY}/library/node:20-alpine AS builder

RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

WORKDIR /app

# 先复制依赖文件，利用 Docker 缓存
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# 再复制源代码
COPY . .
RUN pnpm run build

# ---------- 运行阶段 ----------
FROM ${BASE_REGISTRY}/library/nginx:1.25-alpine

# 健康检查需要 curl
RUN apk add --no-cache curl

# nginx 配置模板（envsubst 替换后端地址）
COPY deploy/default.conf.template /etc/nginx/templates/default.conf.template
COPY deploy/start.sh /docker-entrypoint.d/start.sh
RUN chmod +x /docker-entrypoint.d/start.sh

# 构建产物
COPY --from=builder /app/dist /usr/share/nginx/html
