FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHON=/usr/local/bin/python
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir piper-tts==1.8.0
WORKDIR /app
COPY astra_hybrid /app/astra_hybrid
RUN useradd --system --uid 10001 --create-home astra \
    && mkdir -p /data /models \
    && chown -R astra:astra /app /data
USER 10001:10001
ENV ASTRA_CLOUD_HOST=0.0.0.0 ASTRA_CLOUD_PORT=8765 ASTRA_CLOUD_ALLOW_PUBLIC_BIND=1 \
    ASTRA_KNOWLEDGE_DB=/data/knowledge_hub.sqlite3
EXPOSE 8765
CMD ["python", "-m", "astra_hybrid.cloud_server"]
