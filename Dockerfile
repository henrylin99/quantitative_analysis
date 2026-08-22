FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# 统一容器时区为北京时间：内部时间戳与 A 股行情数据的时区语义一致
ENV TZ=Asia/Shanghai

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements_minimal.txt ./
RUN pip install --no-cache-dir -r requirements_minimal.txt

COPY . .

RUN mkdir -p /app/instance /app/data \
    && useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/', timeout=3).status < 500 else 1)" || exit 1

# 生产：gunicorn + eventlet worker（自动 monkey_patch，支撑 WebSocket）
CMD ["gunicorn", "--worker-class", "eventlet", "--workers", "1", "--bind", "0.0.0.0:5000", "--timeout", "300", "run:app"]
