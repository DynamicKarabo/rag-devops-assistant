# PREP — RAG DevOps Assistant: Production-Ready Completion

**Date:** 2026-05-14  
**Status:** Awaiting approval

---

## 1. Current State

| Component | Status | Detail |
|-----------|--------|--------|
| Ingestion pipeline | ✅ Complete | Crawl → chunk → embed → Qdrant. 12,940 pts in `devops_docs` |
| FastAPI | ✅ Complete | `/query`, `/health`, `/metrics` — lifeycle-managed, OTel middleware |
| Retrieval | ✅ Working | Hybrid search (dense + sparse), ~1.4s latency |
| Docker image | ✅ Built | `ghcr.io/dynamickarabo/rag-devops-assistant:latest` |
| k3s manifests | ✅ Written | `rag-api.yaml`, `qdrant.yaml` in `mlops` namespace |
| Unit tests | ✅ Exists | `tests/test_api.py` — basic coverage |
| CI (GitHub Actions) | ✅ Exists | Build + push to GHCR |
| **Observability dashboards** | 🔴 **Empty** | `observability/` dir exists, zero files |
| **Evaluation framework** | 🔴 **Empty** | `eval/` dir exists, zero files |
| **k3s deployment** | 🔴 **Evicted** | All pods evicted — 92% disk, 14GB reclaimable |
| **LLM wire-up** | 🔴 **Placeholder** | API key in k3s Secret is `PLACEHOLDER` |
| **Cost tracking** | 🔴 **Missing** | Generator logs tokens but no aggregation/dashboard |
| **Alerting** | 🔴 **Missing** | No latency/error/cost alerts |

**Bottom line:** The engine is built. The gauges on the dashboard are blank, and the engine isn't running because the garage (k3s) is full of junk.

---

## 2. What "Production-Ready" Means Here

From the project brief and real job postings, the differentiators are:

1. **Observability** — traces, latency percentiles, cost-per-query, token usage, retrieval metrics. Grafana dashboard an interviewer can look at.
2. **Evaluation in CI** — RAGAS metrics (faithfulness, context recall, answer relevance) run on every PR. Regression testing for retrieval quality.
3. **Deployment pipeline** — GHCR push → k3s deploy → health check → green. No manual steps.
4. **Documentation that sells** — architecture diagram, demo GIF, README that screams "I deploy RAG, not just demo it."

---

## 3. Implementation Plan

### Phase 1: Stabilize the Foundation (30 min)

**Goal:** Get k3s healthy. Reclaim disk. API running in k3s with real API key.

| Task | Detail |
|------|--------|
| 1.1 | Clean Docker: `docker system prune -af --volumes` — reclaim ~8GB |
| 1.2 | Evict old k3s pods, clean exited containers |
| 1.3 | Verify disk >20% free |
| 1.4 | Re-deploy rag-api to k3s with proper resource limits |
| 1.5 | User provides OpenRouter API key → update k3s Secret |
| 1.6 | Verify end-to-end: query → retrieval → generation → response |

**Verification:** `curl -X POST http://178.105.76.236:8000/query` returns a real answer with citations.

---

### Phase 2: Observability Stack (1 hour)

**Goal:** Grafana dashboard that shows latency, cost, tokens, retrieval stats. This is THE portfolio piece.

| Task | Detail |
|------|--------|
| 2.1 | Design dashboard panels: query latency (p50/p95/p99), tokens per query, cost per query, retrieval count, error rate |
| 2.2 | Write Grafana dashboard JSON → `observability/rag-dashboard.json` |
| 2.3 | Import to existing Grafana (already running on VPS) |
| 2.4 | Add cost estimation: `tokens × model_rate` in generator.py |
| 2.5 | Expose cost as Prometheus counter metric |
| 2.6 | Verify Prometheus scraping `/metrics` from k3s pod |
| 2.7 | Screenshot dashboard → add to README |

**Verification:** Grafana dashboard at `http://178.105.76.236:3000` showing live metrics after 5-10 queries.

---

### Phase 3: Evaluation Framework (1.5 hours)

**Goal:** RAGAS evaluation in CI. Every PR tests retrieval quality.

| Task | Detail |
|------|--------|
| 3.1 | Create benchmark dataset: 20 Q&A pairs with ground truth (`eval/benchmark.json`) |
| 3.2 | Write eval script: `eval/run_eval.py` — RAGAS faithfulness, recall, relevance |
| 3.3 | Add eval step to CI: `.github/workflows/ci.yml` — runs on PR |
| 3.4 | Set quality gates: faithfulness ≥ 0.7, recall ≥ 0.6, relevance ≥ 0.7 |
| 3.5 | Add eval results to CI summary (PR comment or job output) |
| 3.6 | Run baseline eval → document scores in README |

**Verification:** PR opened → CI runs eval → passes quality gates → merge.

---

### Phase 4: Polish & Portfolio (1 hour)

**Goal:** Documentation that gets interviews.

| Task | Detail |
|------|--------|
| 4.1 | Architecture diagram (SVG or Excalidraw) → `observability/architecture.png` |
| 4.2 | Demo GIF: ask question → get answer with citations (terminal recording) |
| 4.3 | Update README: architecture, dashboard screenshot, eval scores, quickstart |
| 4.4 | Add `CONTRIBUTING.md` with eval-first workflow |
| 4.5 | Add cost comparison: "This query cost $0.0003 vs $0.01 for GPT-4 direct" |
| 4.6 | Git tag `v1.0.0` — production release |

**Verification:** Someone clones the repo, runs `docker compose up`, and has a working RAG system with dashboards in <5 min.

---

## 4. Tech Decisions (Already Made / Confirmed)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vector DB | Qdrant (Docker, not k3s) | Already running. k3s Qdrant adds complexity for no gain. API connects via node IP. |
| Embeddings | all-MiniLM-L6-v2 (384d) | CPU-only, fast, good enough for docs. No GPU needed. |
| LLM | OpenRouter → DeepSeek V3 / GPT-4o-mini | Multi-provider flexibility. Cost tracking per model. |
| Observability | Prometheus + Grafana (existing VPS stack) | Already running. Zero new infra. |
| Eval | RAGAS | Industry standard. Built-in metrics. |
| CI | GitHub Actions → GHCR | Already configured. Just needs eval step. |
| Deployment | k3s (single-node) | Already running. Service exposed via NodePort or Ingress. |

---

## 5. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Disk fills again | k3s evicts pods → API down | Resource limits on pods. Regular `docker system prune` cron. Monitor disk in Grafana. |
| API key exposed in repo | Security incident | `.env` in `.gitignore`. k3s Secret for prod. Never commit keys. |
| Embedding model too heavy for VPS | Slow startup, OOM kills | all-MiniLM is 90MB. Already tested — loads in ~3s on CX33. |
| RAGAS eval slow in CI | CI times out | Run on GH Actions. 20 Q&As × ~2s each = 40s. Cache model. |
| Qdrant goes down | API returns 503 | Health check in API. Docker restart policy: always. Alert in Grafana. |

---

## 6. What We're NOT Doing (Scope Boundary)

- ❌ **Not** migrating Qdrant to k3s — Docker works, don't fix what isn't broken
- ❌ **Not** building a UI — API-first, curl + Grafana demos
- ❌ **Not** fine-tuning a model — separate project (#1 in your list)
- ❌ **Not** multi-agent orchestration — separate project (#2 in your list)
- ❌ **Not** AWS deployment — $0 budget. VPS only.
- ❌ **Not** .NET — never, ever

---

## 7. Time Estimate

| Phase | Time |
|-------|------|
| Phase 1: Stabilize | 30 min |
| Phase 2: Observability | 1 hr |
| Phase 3: Evaluation | 1.5 hr |
| Phase 4: Polish | 1 hr |
| **Total** | **~4 hours** |

---

## 8. Approval Gates

1. **Phase 1 done** → API returns real answers in k3s. Stop. You verify.
2. **Phase 2 done** → Grafana dashboard shows live metrics. Stop. You verify.
3. **Phase 3 done** → `python -m eval.run_eval` passes quality gates. Stop. You verify.
4. **Phase 4 done** → README is interview-ready. Tag v1.0.0.

**After each gate:** you say "next" and we move.

---

## 9. What I Need From You

- **OpenRouter API key** — for Phase 1 (k3s Secret) and Phase 3 (eval). Without it, LLM calls return 401.
- **Approval on domain scope** — currently ingesting Kubernetes + Docker + Terraform docs. Want to add anything? (GitHub Actions? Ansible? Helm?)
- **Go / no-go on this plan.**
