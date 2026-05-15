"""
RAG DevOps Assistant — FastAPI application.
Endpoints: /query, /health, /metrics
"""

import os
import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

from api.models import QueryRequest, QueryResponse, SourceCitation, HealthResponse
from api.retriever import Retriever
from api.generator import Generator
from api.middleware import setup_observability
from api.metrics import (
    rag_query_latency, rag_retrieval_latency, rag_llm_latency,
    rag_tokens_total, rag_sources_per_query, rag_cost_total,
    rag_qdrant_points, rag_qdrant_up, rag_errors_total,
)
from ingest.embedder import Embedder

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "devops_docs")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")

# ── Global state ────────────────────────────────────────
embedder: Embedder | None = None
retriever: Retriever | None = None
generator: Generator | None = None
_ready: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models on startup, clean up on shutdown."""
    global embedder, retriever, generator, _ready

    logger.info("Starting RAG DevOps Assistant...")
    logger.info(f"Qdrant: {QDRANT_URL} / {QDRANT_COLLECTION}")
    logger.info(f"LLM: {LLM_MODEL}")

    try:
        logger.info("Loading embedding model...")
        embedder = Embedder()
        logger.info("Embedding model loaded.")

        logger.info("Initializing retriever...")
        retriever = Retriever(QDRANT_URL, QDRANT_COLLECTION, embedder)

        logger.info("Initializing generator...")
        generator = Generator(model=LLM_MODEL)
        logger.info("Generator initialized.")

        # Verify Qdrant connection (non-blocking, quick check)
        try:
            info = retriever.client.get_collection(QDRANT_COLLECTION)
            logger.info(f"Connected to Qdrant: {info.points_count} points in {QDRANT_COLLECTION}")
        except Exception as e:
            logger.warning(f"Qdrant connection check failed (ingest first?): {e}")

        _ready = True
        logger.info("RAG API ready.")
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        # Don't block — allow /health to report not-ready

    yield

    logger.info("Shutting down.")
    _ready = False


app = FastAPI(
    title="RAG DevOps Assistant",
    description="Production RAG system for DevOps documentation — observability-first with evaluation in CI",
    version="0.1.0",
    lifespan=lifespan,
)

setup_observability(app)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check — verifies Qdrant connectivity and model state."""
    # ── Health check with Qdrant metrics ──
    qdrant_points = 0
    qdrant_ok = False
    if retriever:
        try:
            info = retriever.client.get_collection(QDRANT_COLLECTION)
            qdrant_points = info.points_count or 0
            qdrant_ok = True
        except Exception:
            pass

    rag_qdrant_points.set(qdrant_points)
    rag_qdrant_up.set(1 if qdrant_ok else 0)

    return HealthResponse(
        status="ok" if _ready else "starting",
        qdrant_points=qdrant_points,
        model_loaded=embedder is not None,
        version="0.1.0",
    )


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    """
    Answer a DevOps question using RAG.
    1. Retrieve relevant chunks from Qdrant
    2. Generate answer with LLM
    3. Return answer + citations
    """
    if not _ready or not retriever or not generator:
        rag_errors_total.labels(error_type="503_not_ready").inc()
        raise HTTPException(status_code=503, detail="Service not ready — models still loading")

    t0 = time.monotonic()

    # ── Retrieve (with timing) ──
    t_retrieve = time.monotonic()
    chunks = retriever.search(req.question, top_k=req.top_k)
    retrieval_ms = (time.monotonic() - t_retrieve) * 1000
    rag_retrieval_latency.observe(retrieval_ms / 1000)

    # ── Generate (LLM call) ──
    result = generator.generate(req.question, chunks)

    # ── Build sources ──
    sources = []
    if req.include_sources:
        for chunk in chunks:
            sources.append(SourceCitation(
                url=chunk.get("url", ""),
                title=chunk.get("title", "Unknown"),
                snippet=chunk["text"][:200] + ("..." if len(chunk["text"]) > 200 else ""),
            ))

    latency_ms = (time.monotonic() - t0) * 1000

    # ── Record metrics ──
    rag_query_latency.observe(latency_ms / 1000)
    rag_retrieval_latency.observe(retrieval_ms / 1000)
    llm_s = result.get("llm_latency_s", 0)
    if llm_s > 0:
        rag_llm_latency.observe(llm_s)
    rag_sources_per_query.observe(len(sources))
    tokens = result.get("tokens_used", 0)
    if tokens > 0:
        rag_tokens_total.inc(tokens)

    # Cost estimation: ~$0.0005/1K tokens for free-tier inference
    if tokens > 0:
        cost = tokens * 0.0000005
        rag_cost_total.inc(cost)

    if result["answer"].startswith("Error"):
        rag_errors_total.labels(error_type="llm_error").inc()

    logger.info(f"Query complete: {latency_ms:.1f}ms, {tokens} tokens, {len(sources)} sources")

    return QueryResponse(
        question=req.question,
        answer=result["answer"],
        sources=sources,
        tokens_used=result["tokens_used"],
        latency_ms=latency_ms,
        model=result["model"],
    )
