# === VideoNote 后端 Dockerfile ===
# Python 3.13 + uv + ffmpeg

FROM python:3.13-slim AS builder

# uv 官方安装
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 系统依赖：ffmpeg（音频提取）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先复制依赖定义，利用 Docker 层缓存
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 再复制源码
COPY app/ app/
COPY alembic.ini migrations/ ./
COPY config.yaml ./

# 安装项目
RUN uv sync --frozen --no-dev

EXPOSE 8000

# 绑定 0.0.0.0 才能接受容器外请求
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
