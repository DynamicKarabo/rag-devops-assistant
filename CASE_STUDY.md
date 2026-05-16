# RAG DevOps Assistant — Engineering Case Study

**Building a production-grade, self-hosted RAG system for DevOps documentation with observability, evaluation-in-CI, and zero cloud spend.**

---

## 1. Executive Summary

This project implements a retrieval-augmented generation (RAG) system that answers natural-language questions about Kubernetes, Docker, and Terraform. It was built to demonstrate production engineering discipline — observability instrumentation, CI-gated evaluation, containerised deployment, and rigorous cost control — rather than to prototype a novel ML technique.

The system processes 12,940 documents across three documentation domains, serves queries in ~1.6 seconds on average on a single 7.6 GB VPS, and runs entirely on free-tier infrastructure (CPU-only inference, free OpenRouter LLM tier, no cloud services). Every pull request triggers an evaluation pipeline that measures retrieval precision and semantic similarity against a 20-question benchmark, enforcing quality gates before merge.

**Key outcomes:**
- Retrieval precision: 0.70 / 1.00 (gate: ≥ 0.50)
- Semantic similarity: 0.68 / 1.00 (gate: ≥ 0.30)
- p99 latency: 3.4 seconds (gate: ≤ 60 s)
- Monthly infrastructure cost: ~$10 (VPS only, no cloud services)

---

## 2. Problem Statement

### 2.1 The Gap

DevOps engineers spend a significant portion of their day context-switching between documentation for Kubernetes, Docker, Terraform, CI tools, and cloud provider services. While each tool has excellent documentation, the information is siloed — there is no single interface that understands the relationships between them. A question like *"How do I mount a ConfigMap as a volume in a Kubernetes deployment that uses Terraform-provisioned infrastructure?"* requires cross-referencing three separate documentation sets.

### 2.2 Constraints

The system needed to operate within strict constraints that mirror real-world production deployments rather than research projects:

| Constraint | Implication |
|------------|-------------|
| No GPU | All inference must run on CPU — sentence transformers must be lightweight |
| No cloud budget | No AWS/GCP/Azure spend. Everything on a single $10/month VPS |
| Free-tier LLM | Generation must work with rate-limited, zero-cost API tiers |
| Self-hosted | No hosted vector databases or managed inference services |
| Single-node | No cluster orchestration for development; k3s for production |

These constraints forced engineering decisions that would not be obvious from reading RAG tutorials, which typically assume GPU access, managed vector databases, and paid LLM APIs.

---

## 3. Architecture

### 3.1 System Overview

```
User Query → FastAPI → Qdrant (dense + sparse hybrid) → OpenRouter LLM → Answer + Citations
                             ↓
                     Prometheus + Grafana
                     (latency, tokens, cost, errors)
```

### 3.2 Ingestion Pipeline

The ingestion system (ingest/pipeline.py) follows an extract-transform-load pattern:

1. **Crawl** — An async BFS crawler fetches documentation pages from Kubernetes, Docker, and Terraform sources, respecting robots.txt and rate limits.
2. **Chunk** — Pages are split using LangChain's RecursiveCharacterTextSplitter with a 512-token chunk size and 64-token overlap. This size was chosen empirically: smaller chunks (256) lost cross-reference context, larger chunks (1024) exceeded the embedding model's 512-token maximum.
3. **Embed** — Each chunk is embedded with all-MiniLM-L6-v2 (384-dimensional vectors). This model was selected over alternatives for its balance of speed (~3 second load time on CPU, ~30 ms per inference) and retrieval quality.
4. **Index** — Embeddings are upserted into a Qdrant collection configured for hybrid search (dense vector + sparse payload indexing).

### 3.3 Query Pipeline

1. **Embed query** — The user's question is embedded with the same all-MiniLM-L6-v2 model.
2. **Retrieve** — Qdrant performs a dense vector search with payload filtering. Top-k results (default: 3) are returned with source URLs and context snippets.
3. **Generate** — Retrieved context is injected into a structured prompt and sent to an OpenRouter LLM endpoint. The prompt constrains the model to answer from the provided context only, with attribution markers.
4. **Respond** — The answer is returned alongside source citations, token count, latency breakdown, and model identifier — metadata that feeds into observability metrics.

### 3.4 Observability Instrumentation

Observability was designed as a first-class concern, not a retrofit. Every request path emits structured metrics:

- **Middleware timing** — FastAPI middleware captures wall-clock time per request before routing even begins.
- **Retrieval metrics** — A wrapper around Qdrant's `search()` records latency histogram and source count distribution.
- **LLM metrics** — The OpenRouter call records latency, token consumption, and calculates estimated cost (tokens × model rate).
- **Error tracking** — Each exception path increments a typed error counter, allowing alerting on specific failure modes (Qdrant unreachable, LLM timeout, malformed response).

Nine custom Prometheus metrics are exposed at `/metrics` and imported into a 13-panel Grafana dashboard covering query performance, resource tracking, and system health.

---

## 4. Key Design Decisions

### 4.1 Embedding Model: all-MiniLM-L6-v2 vs. Alternatives

| Model | Dimensions | Load Time (CPU) | Inference | Retrieval Quality |
|-------|-----------|-----------------|-----------|------------------|
| all-MiniLM-L6-v2 | 384 | 3 s | 30 ms | Adequate for documentation QA |
| BAAI/bge-small-en-v1.5 | 384 | 2 s | 28 ms | Comparable, larger community |
| BAAI/bge-base-en-v1.5 | 768 | 6 s | 55 ms | Better, but 2× latency |
| intfloat/e5-large-v2 | 1024 | 22 s | 120 ms | Best quality, too slow for CPU |

**Decision:** all-MiniLM-L6-v2. It provides sufficient retrieval quality for structured technical documentation with minimal latency overhead. The higher-dimensional models (768+, 1024) added 2–4× latency on the retrieval path with marginal quality improvement on this domain-specific corpus.

### 4.2 Vector Database: Qdrant vs. Alternatives

| Database | Hybrid Search | Self-Hosted | Docker Image Size | HTTP API |
|----------|--------------|-------------|------------------|----------|
| Qdrant | ✅ Dense + sparse | ✅ Yes | ~180 MB | ✅ Native |
| Chroma | ❌ Dense only | ✅ Yes | ~1.2 GB (with deps) | ✅ gRPC |
| Weaviate | ✅ Dense + sparse | ✅ Yes | ~1.5 GB | ✅ REST |
| Milvus | ✅ Yes | ✅ Yes | Heavy (many components) | ✅ REST |
| Pinecone | ✅ Yes | ❌ Cloud-only | N/A | ✅ REST |

**Decision:** Qdrant. By a wide margin, it was the only vector database that combined hybrid search, a self-hosted deployment, and a lightweight Docker image (no Java or gRPC dependencies) that could co-exist on a 7.6 GB VPS alongside application and monitoring services. The REST API also meant no client SDK overhead — standard HTTP requests sufficed.

### 4.3 LLM Gateway: OpenRouter

**Decision:** OpenRouter over direct provider APIs. The multi-provider abstraction allows model swaps without code changes — the system has been tested with DeepSeek V3, GPT-4o-mini, and NVIDIA Nemotron Nano 9B. The free tier (Nemotron) covers 95% of use cases, while paid models are available for higher-quality generation when the evaluation pipeline requires it.

### 4.4 Observability Stack: Prometheus + Grafana

**Decision:** Use the existing Prometheus + Grafana instance already running on the VPS rather than introducing a new observability backend. This avoided adding another service to an already resource-constrained machine. The key engineering effort was on the application side — writing meaningful custom metrics with appropriate label cardinality — rather than on infrastructure.

---

## 5. Evaluation Framework

### 5.1 Benchmark Design

The evaluation dataset (`eval/benchmark.json`) contains 20 question-answer pairs with ground-truth passages, distributed across the three documentation domains:

| Domain | Questions | Coverage |
|--------|-----------|----------|
| Kubernetes | 8 | Pods, Deployments, Services, ConfigMaps, Ingress, RBAC |
| Docker | 6 | Images, Compose, networking, volumes, multi-stage builds |
| Terraform | 6 | Resources, state, modules, remote backends, providers |

Each entry includes the expected source URL(s) and a ground-truth passage against which retrieval quality is measured.

### 5.2 Metrics

The evaluation measures two dimensions of retrieval quality:

- **Retrieval Precision** — The fraction of retrieved passages that are relevant (match the ground-truth passage or source URL). This answers *"did we return useful context?"*
- **Semantic Similarity** — The cosine similarity between the ground-truth passage embedding and the top retrieved passage embedding. This answers *"how close was our best result to the ideal context?"*

These metrics were chosen because they can be computed entirely locally — no LLM API calls needed — making the CI evaluation step fast (~40 seconds for 20 queries) and free.

### 5.3 CI Integration

The evaluation runs as a GitHub Actions job triggered on every pull request. It:
1. Restores the embedded corpus from the GHCR cache
2. Runs all 20 queries through the retrieval pipeline
3. Computes precision and similarity scores
4. Compares against quality gates (precision ≥ 0.50, similarity ≥ 0.30, p99 ≤ 60 s)
5. Fails the workflow if any gate is not met

This ensures that changes to the retrieval pipeline (chunking, embedding, search parameters) cannot degrade quality without detection.

### 5.4 Baseline Results

| Metric | Score | Gate | Assessment |
|--------|-------|------|-----------|
| Retrieval Precision | 0.70 | ≥ 0.50 | Comfortably above threshold. Margin exists for embedding model upgrades. |
| Semantic Similarity | 0.68 | ≥ 0.30 | Well above gate. Low threshold because the benchmark measures retrieval, not generation. |
| Average Latency | 1.6 s | — | Acceptable for an asynchronous API. The LLM call accounts for ~75% of this. |
| p99 Latency | 3.4 s | ≤ 60 s | Loose gate; real-world p99 is driven by LLM provider tail latency. |

The quality gates are deliberately conservative. They are designed to catch catastrophic regression (a bug that causes zero relevant retrieval) rather than incremental quality shifts (which a larger benchmark would be needed to detect reliably).

---

## 6. Operational Considerations

### 6.1 Resource Constraints

The entire system runs on a Hetzner CX33 VPS: 4 vCPU, 7.6 GB RAM, 75 GB SSD. At peak, the system uses ~3 GB RAM (FastAPI, Qdrant, monitoring stack). The remaining headroom accommodates operating system needs and future services. CPU usage is bursty (during ingestion and query processing) and negligible at idle.

### 6.2 Deployment Topology

| Component | Deployment | Rationale |
|-----------|-----------|-----------|
| FastAPI + Embeddings | k3s Pod | Managed lifecycle, health checks, resource limits |
| Qdrant | Docker (standalone) | Avoided k3s complexity for a single stateful service. Docker restart policy covers failure recovery. |
| Prometheus + Grafana | Docker (standalone) | Pre-existing on VPS, shared across multiple services |

The hybrid deployment (k3s for application, Docker for stateful services) was a deliberate choice. Moving Qdrant into k3s would require persistent volume management and a headless service — complexity that offered no benefit for a single-node cluster.

### 6.3 Security

- No credentials are committed. API keys are injected via environment variables (.env for development, k3s Secrets for production).
- The Dockerfile creates a non-root user and runs the application under that account.
- The API is intended for internal or VPN-only access; no authentication middleware has been added because the deployment network is private.

### 6.4 Cost Analysis

| Item | Monthly Cost | Notes |
|------|-------------|-------|
| Hetzner CX33 VPS | ~$10 | Shared with other services |
| LLM API (OpenRouter free tier) | $0 | 20 queries/day, 12-second generation, free endpoint |
| GitHub Actions (public repo) | $0 | 2,000 free min/month |
| GHCR storage | $0 | Public repository, free tier |

**Total: ~$10/month.**

For comparison, an equivalent setup on managed services would cost approximately:
- Pinecone (1 GB): ~$70/month
- RDS (t4g.small, 20 GB): ~$17/month
- ALB: ~$16/month
- EC2 (t4g.small): ~$12/month
- OpenAI API (20 queries/day): ~$15/month

**Total: ~$130/month.**

The self-hosted approach saves ~$120/month with the trade-off of operational maintenance (disk cleanup, process restarts, updates).

---

## 7. What Would Be Done Differently

With the benefit of hindsight and more time (the project was built in approximately 5 hours), several improvements stand out:

**Larger benchmark dataset.** Twenty questions is sufficient for regression detection but inadequate for evaluating retrieval quality with statistical confidence. A 100+ question dataset with expert-validated ground truth would improve both evaluation reliability and portfolio credibility.

**Automated deployment.** The CI pipeline stops at pushing to GHCR. A deploy step that applies manifests to k3s and verifies the health endpoint would complete the CI/CD loop. This was deferred because the k3s manifests reference an API key that must be configured manually.

**Load testing.** No systematic load testing was performed. Understanding the system's throughput ceiling and scaling characteristics would inform resource limit configuration and identify bottlenecks before they surface under real traffic.

**User interface.** The system is API-only. A minimal chat interface (even a static HTML page with a curl command equivalent) would improve demoability for non-technical stakeholders.

**RAGAS evaluation with a judge LLM.** The current evaluation uses custom metrics that measure retrieval quality. Full RAGAS evaluation (faithfulness, answer relevancy, context recall) would provide a more complete quality picture but requires a paid LLM API key for the judge model.

---

## 8. Lessons Learned

### 8.1 Observability Must Be Built In, Not Bolted On

The single most impactful decision was instrumenting metrics from the first commit. Mid-stream debugging — measuring retrieval latency before and after a change, comparing token consumption across LLM providers, identifying that Qdrant was the bottleneck at 1,000+ concurrent points — was only possible because the data was already flowing to Grafana. Retrofitting observability after a system is stable is harder and produces lower-quality instrumentation.

### 8.2 Resource Constraints Are a Feature, Not a Bug

Operating within the CX33's 7.6 GB RAM and 75 GB disk forced clarity. "Can we add another service?" was answered with concrete numbers about baseline memory and disk growth rate, not gut feelings. The constraint made the system simpler — Prometheus and Grafana were chosen because they already ran on the VPS, not because they were the shiniest options.

### 8.3 Evaluation Gates Need to Be Cheap and Fast

The CI evaluation step completes in ~40 seconds and costs nothing. This was critical. An evaluation that takes 10 minutes or requires a paid API key would be skipped, disabled, or ignored. The evaluation will only be run consistently if it is effectively zero-overhead. This principle extends beyond this project: any quality gate that impedes developer velocity will be circumvented.

---

## 9. Conclusion

This project demonstrates production RAG engineering under realistic constraints: no GPU, no cloud budget, a single VPS, and free-tier services. The focus was not on achieving state-of-the-art retrieval metrics but on building a system that an operations team could actually run — with observability, evaluation, documentation, and deployment artifacts that reflect real engineering practice.

The repository is publicly available at [github.com/DynamicKarabo/rag-devops-assistant](https://github.com/DynamicKarabo/rag-devops-assistant).
