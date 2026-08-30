FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8080

# 安装系统依赖（python-telegram-bot 不需要额外系统依赖）
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，利用 Docker 缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY bot.py webapp.py ./
COPY templates/ ./templates/

# 创建数据目录（数据文件会写入这里，建议挂载持久卷）
RUN mkdir -p /app/data
ENV BOT_DATA_FILE=/app/data/bot_data.json

# 暴露 Web 后台端口
EXPOSE 8080

# 健康检查（可选，Render 会用它判断服务是否存活）
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/login')" || exit 1

# 启动机器人（同时运行 Telegram polling 和 Web 后台）
CMD ["python", "bot.py"]
