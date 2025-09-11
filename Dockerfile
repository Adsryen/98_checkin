# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 系统依赖（如需可按需扩展）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# 复制依赖并安装
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 复制源码与示例配置
COPY sehuatang_bot /app/sehuatang_bot
COPY config.example.yaml /app/config.example.yaml

# 缺省环境变量（可在运行时覆盖）
ENV CONFIG_PATH=/app/config.yaml \
    SITE_BASE_URL= \
    SITE_USERNAME= \
    SITE_PASSWORD= \
    SITE_MIRROR_URLS= \
    SITE_UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36" \
    AI_API_KEY= \
    AI_BASE_URL= \
    AI_MODEL=gpt-4o-mini \
    AI_TEMPERATURE=0.5 \
    AI_MAX_TOKENS=200 \
    BOT_DRY_RUN=true \
    BOT_REPLY_ENABLED=false \
    BOT_REPLY_FORUMS= \
    BOT_SIGNATURE="—— 来自自动化小助手" \
    BOT_DAILY_CHECKIN_ENABLED=true

ENTRYPOINT ["python", "-m", "sehuatang_bot"]
CMD ["run-all"]
