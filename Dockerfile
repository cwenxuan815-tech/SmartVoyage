# SmartVoyage 统一镜像：同一镜像 + 不同启动命令/环境变量 = 不同服务
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HOST=0.0.0.0

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc pkg-config default-libmysqlclient-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY SmartVoyage ./SmartVoyage
COPY scripts ./scripts
COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh \
    && mkdir -p /app/logs /app/data

EXPOSE 5005 5006 5007 8001 8002 8003 8080

ENTRYPOINT ["/entrypoint.sh"]
CMD ["api_server"]
