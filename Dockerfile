# ============================================
# 阶段 1: 构建层 (Builder)
# 安装编译依赖，构建 Python 包
# ============================================
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 升级 pip 并创建虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 安装 Python 依赖（利用 Docker 缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ============================================
# 阶段 2: 运行层 (Runtime)
# 仅复制必要的运行时文件
# ============================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# 安装运行时依赖（libpq 用于 PostgreSQL 连接）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser \
    && useradd -r -g appuser appuser

# 从构建层复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

# 复制配置文件
COPY config/ /app/config/

# 复制后端代码
COPY backend/ /app/backend/

# 复制前端静态资源
COPY frontend/ /app/frontend/

# 复制 gunicorn 配置
COPY gunicorn.conf.py /app/

# 修正权限
RUN chown -R appuser:appuser /app
USER appuser

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# 暴露端口
EXPOSE 8000

# 启动命令（gunicorn + uvicorn workers）
CMD ["gunicorn", "main:app", \
     "-c", "/app/gunicorn.conf.py"]
