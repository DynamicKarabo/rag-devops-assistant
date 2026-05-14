# Multi-stage Dockerfile
# Stage 1: build deps + pre-download embedding model
# Stage 2: slim runtime

FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

# Install all runtime deps (CPU-only PyTorch to save ~1GB)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir \
        fastapi>=0.133.0 \
        "uvicorn[standard]>=0.41.0" \
        qdrant-client>=1.14.0 \
        sentence-transformers>=3.0.0 \
        openai>=2.24.0 \
        langchain-text-splitters>=0.3.0 \
        httpx>=0.28.0 \
        prometheus-fastapi-instrumentator>=7.1.0 \
        opentelemetry-api>=1.30.0 \
        opentelemetry-sdk>=1.30.0 \
        opentelemetry-instrumentation-fastapi>=0.51b0 \
        opentelemetry-exporter-otlp>=1.30.0 \
        pydantic>=2.0.0 \
        python-dotenv>=1.0.0 \
    && pip cache purge

# Pre-download embedding model
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# ---- runtime ----
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy model cache
COPY --from=builder /root/.cache /root/.cache

# Copy app code
COPY api/ ./api/
COPY ingest/ ./ingest/

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app /root/.cache
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
