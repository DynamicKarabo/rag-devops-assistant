# RAG DevOps Assistant

**Production RAG system for DevOps documentation — observability-first with evaluation in CI.**

Ask natural language questions about Kubernetes, Docker, and Terraform. Get answers with source citations, latency tracking, and cost monitoring.

[![CI](https://github.com/DynamicKarabo/rag-devops-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/DynamicKarabo/rag-devops-assistant/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Architecture

![Architecture Diagram](observability/architecture.html)

```
User Query → FastAPI → Qdrant (hybrid search) → OpenRouter LLM → Answer + Citations
                                ↓
                        Prometheus + Grafana
                        (latency, cost, tokens)
```

## Why This Project

This isn't a RAG demo. It's a **production deployment** that an interviewer can inspect:

- **Observability from day one** — Custom Prometheus metrics, 13-panel Grafana dashboard with latency percentiles, token tracking, and cost estimation
- **Evaluation in CI** — 20-question benchmark with retrieval precision and semantic similarity gates on every PR
- **Real deployment** — Multi-stage Docker builds, k3s manifests, health checks, resource limits
- **Zero-cost LLM** — Free tier OpenRouter with NVIDIA Nemotron Nano 9B (12s avg, free)

Companies need engineers who can **deploy RAG, not just demo it.** This is that portfolio piece.

## Quick Start

```bash
# 1. Start Qdrant
docker compose up -d qdrant

# 2. Ingest docs (first time)
cp .env.example .env  # add your OpenRouter API key
docker compose --profile ingest run --rm ingest

# 3. Start the API
docker compose up -d api

# 4. Ask a question
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How do I create a Kubernetes deployment?"}'
```

## Baseline Evaluation Scores

| Metric | Score | Gate |
|--------|-------|------|
| Retrieval Precision | **0.70** | ≥ 0.50 ✅ |
| Semantic Similarity | **0.68** | ≥ 0.30 ✅ |
| Avg Latency | **1.6s** | — |
| p99 Latency | **3.4s** | ≤ 60s ✅ |
| Qdrant Points | **12,940** | — |

*Full RAGAS evaluation (faithfulness, answer relevancy, context recall) requires a paid OpenRouter API key for the judge LLM. Documented in `eval/run_eval.py`.*

## Observability Dashboard

![Grafana Dashboard](observability/rag-dashboard.json)

**13 panels** covering:
- Query rate (req/min), avg latency, tokens consumed, cost estimation
- Latency percentiles (p50/p95/p99) and retrieval vs LLM breakdown
- Sources per query distribution, error rate by type
- Qdrant health (points count, up/down status)
- API request throughput by endpoint

Dashboard auto-loaded at `http://178.105.76.236:3000` → "RAG DevOps Assistant"

## Custom Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `rag_query_latency_seconds` | Histogram | Total query latency |
| `rag_retrieval_latency_seconds` | Histogram | Qdrant search time |
| `rag_llm_latency_seconds` | Histogram | LLM API call time |
| `rag_tokens_total` | Counter | Total tokens consumed |
| `rag_cost_total` | Counter | Estimated USD cost |
| `rag_sources_per_query` | Histogram | Retrieved sources count |
| `rag_qdrant_points` | Gauge | Points in collection |
| `rag_qdrant_up` | Gauge | Qdrant reachable (1/0) |
| `rag_errors_total` | Counter | Errors by type |

## Tech Stack

| Layer | Tool | Why |
|-------|------|-----|
| API | FastAPI + Uvicorn | Async, OpenAPI docs, Prometheus built-in |
| Vector DB | Qdrant | Hybrid search (dense + sparse), self-hosted |
| Embeddings | all-MiniLM-L6-v2 (384-dim) | CPU-only, 90MB, fast |
| LLM | OpenRouter → NVIDIA Nemotron Nano 9B | Free tier, 9B params, reliable |
| Chunking | LangChain RecursiveCharacterTextSplitter | Semantic chunking |
| Observability | Prometheus + Grafana | Custom metrics, 13-panel dashboard |
| Evaluation | RAGAS (retrieval) | 20 Q&A benchmark, CI gate |
| Orchestration | Docker Compose (dev) / k3s (prod) | Single-node, flannel networking |
| CI/CD | GitHub Actions → GHCR | Lint → test → eval → build → push |

## Project Structure

```
├── api/            # FastAPI application
│   ├── main.py     # App entry, /query, /health
│   ├── models.py   # Pydantic schemas
│   ├── retriever.py # Qdrant search
│   ├── generator.py # LLM call (OpenRouter)
│   ├── metrics.py  # Custom Prometheus metrics
│   └── middleware.py # OTel + Prometheus
├── ingest/         # Document ingestion pipeline
│   ├── pipeline.py # CLI entry point
│   ├── crawler.py  # Fetch OSS docs
│   ├── chunker.py  # Semantic chunking
│   ├── embedder.py # Sentence transformer
│   └── indexer.py  # Qdrant upsert
├── eval/           # Evaluation framework
│   ├── benchmark.json # 20 Q&A pairs with ground truth
│   └── run_eval.py    # Retrieval precision + semantic similarity
├── observability/  # Grafana dashboards
│   ├── rag-dashboard.json # 13-panel RAG dashboard
│   └── architecture.html # System architecture diagram
├── k3s/            # Kubernetes manifests
│   ├── rag-api.yaml
│   └── qdrant.yaml
├── tests/          # Unit + integration tests
├── docker-compose.yml
├── Dockerfile      # Multi-stage build (CPU-only PyTorch)
└── .github/workflows/ci.yml  # lint → test → eval → build
```

## API Reference

### `POST /query`

Ask a DevOps question. Returns answer with source citations.

```json
// Request
{
  "question": "How do I create a Kubernetes deployment?",
  "top_k": 3,
  "include_sources": true
}

// Response
{
  "answer": "To create a Kubernetes Deployment, define a YAML manifest...",
  "sources": [
    {
      "url": "https://kubernetes.io/docs/concepts/workloads/controllers/deployment/",
      "title": "Deployments | Kubernetes",
      "snippet": "A Deployment provides declarative updates for Pods..."
    }
  ],
  "tokens_used": 438,
  "latency_ms": 4900,
  "model": "nvidia/nemotron-nano-9b-v2:free"
}
```

### `GET /health`

```json
{
  "status": "ok",
  "qdrant_points": 12940,
  "model_loaded": true,
  "version": "1.0.0"
}
```

### `GET /metrics`

Prometheus metrics endpoint. Includes standard HTTP metrics + custom RAG metrics.

## Deployment

### Development (Docker Compose)
```bash
docker compose up -d qdrant api
```

### Production (k3s)
```bash
kubectl apply -f k3s/qdrant.yaml
kubectl apply -f k3s/rag-api.yaml
```

## License

MIT
