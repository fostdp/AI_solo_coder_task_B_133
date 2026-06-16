# ============================================
# Gunicorn 配置文件
# 生产环境：gunicorn + uvicorn workers
# ============================================
import os
import multiprocessing

# 绑定地址
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# Worker 进程数：CPU 核心数 * 2 + 1
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))

# Worker 类型：使用 uvicorn 的异步 worker
worker_class = "uvicorn.workers.UvicornWorker"

# 每个 worker 的最大并发连接数
worker_connections = int(os.getenv("GUNICORN_MAX_CONNECTIONS", "1000"))

# 超时时间（秒）
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))

# 优雅关闭超时
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))

# Keep-Alive 超时
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

# 最大请求数（自动重启，防止内存泄漏）
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "10000"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "1000"))

# 日志配置
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# 进程名称
proc_name = os.getenv("GUNICORN_PROC_NAME", "gongdeng-api")

# 预热加载应用（preload_app=True 可减少内存占用）
preload_app = os.getenv("GUNICORN_PRELOAD", "true").lower() == "true"

# 临时文件目录
raw_env = [
    f"TMPDIR={os.getenv('TMPDIR', '/tmp')}",
]
