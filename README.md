# RAG DevOps Assistant

**Production RAG system for DevOps documentation — observability-first with evaluation in CI.**

Ask natural language questions about Kubernetes, Docker, and Terraform. Get answers with source citations, latency tracking, and cost monitoring.

## Architecture

```
User Query → FastAPI → Qdrant (hybrid search) → OpenRouter LLM → Answer + Citations
                                ↓
                        Prometheus + Grafana
                        (latency, cost, tokens)
```

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

## Key Differentiators

- **Observability-first**: OpenTelemetry traces + Prometheus metrics + Grafana dashboards from day one
- **Evaluation in CI**: RAGAS metrics (faithfulness, recall, relevance) run on every PR
- **Cost tracking**: Every query logs token usage and estimated cost
- **Production deployment**: Multi-stage Docker builds, k3s manifests, health checks, resource limits

## Tech Stack

| Layer | Tool |
|-------|------|
| API | FastAPI + Uvicorn |
| Vector DB | Qdrant |
| Embeddings | all-MiniLM-L6-v2 (384-dim, CPU) |
| LLM | OpenRouter (OpenAI-compatible) |
| Chunking | LangChain RecursiveCharacterTextSplitter |
| Observability | OpenTelemetry + Prometheus + Grafana |
| Evaluation | RAGAS |
| Orchestration | Docker Compose (dev) / k3s (prod) |
| CI/CD | GitHub Actions → GHCR |

## Project Structure

```
├── api/            # FastAPI application
│   ├── main.py     # App entry point, /query, /health
│   ├── models.py   # Pydantic schemas
│   ├── retriever.py # Qdrant search
│   ├── generator.py # LLM call (OpenRouter)
│   └── middleware.py # OTel + Prometheus
├── ingest/         # Document ingestion pipeline
│   ├── pipeline.py # CLI entry point
│   ├── crawler.py  # Fetch OSS docs
│   ├── chunker.py  # Semantic chunking
│   ├── embedder.py # Sentence transformer
│   └── indexer.py  # Qdrant upsert
├── eval/           # Evaluation framework (Phase 3)
├── observability/  # Grafana dashboards (Phase 2)
├── tests/          # Unit + integration tests
├── docker-compose.yml
├── Dockerfile      # Multi-stage build
└── .github/workflows/ci.yml
```

## License

MIT
