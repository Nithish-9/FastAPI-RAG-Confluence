FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/app/model_cache/huggingface
ENV FASTEMBED_CACHE_PATH=/app/model_cache/fastembed

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic-dev \
    gcc \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/model_cache && chmod 755 /app/model_cache

COPY . .

EXPOSE 9900

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:9900/health || exit 1

CMD ["python", "app.py"]