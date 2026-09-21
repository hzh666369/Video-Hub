# Docker 布局说明：本文件与 .dockerignore 必须留在 videohub/ —— 因为下方
# COPY frontend/… 与 COPY backend/… 以 videohub/ 为构建上下文，且 .dockerignore
# 只在构建上下文根目录生效。部署编排层（docker-compose / 一键脚本 / 部署文档）
# 在仓库根的 Docker/ 目录，compose 用 context: ../videohub 指回此处构建。
#
# ========== 阶段一：前端构建（Vue3 + Vite）==========
# Vite 8 要求 Node ^20.19 或 >=22.12，用 22-alpine
FROM node:22-alpine AS frontend-builder

WORKDIR /build/frontend

# 先只拷贝依赖清单，命中层缓存时跳过 npm ci
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# 再拷贝源码构建；vite.config.js 中 outDir=../backend/static，
# 故产物输出到 /build/backend/static
COPY frontend/ ./
RUN npm run build

# ========== 阶段二：后端运行（FastAPI + Uvicorn）==========
FROM python:3.12-slim

WORKDIR /app

# 先装依赖：放一个空 app 包让 pip install . 可构建，命中缓存时跳过安装
COPY backend/pyproject.toml ./
RUN mkdir -p app && touch app/__init__.py \
    && pip install --no-cache-dir .

# 后端源码
COPY backend/app ./app

# 前端产物：app/main.py 默认从 <backend>/static 托管，即 /app/static
COPY --from=frontend-builder /build/backend/static ./static

# 数据（SQLite / 访问日志）统一放 /app/data，compose 里挂卷持久化
ENV VIDEOHUB_DB_URL=sqlite:////app/data/videohub.db \
    VIDEOHUB_LOG_DIR=/app/data/logs \
    TZ=Asia/Shanghai

# 非 root 运行
RUN useradd -m appuser && mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# --no-server-header：抹掉 uvicorn 默认下发的 Server 指纹（2026-09-18 爬虫视角
# 安全测试同类发现项——同类项目被测出 X-Powered-By 后端指纹暴露；Cloudflare 边缘
# 通常已改写该头，这里做纵深防御，任何直接触达源站的路径都不再泄露框架信息）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
