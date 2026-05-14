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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models on startup, clean up on shutdown."""
    global embedder, retriever, generator

    logger.info("Starting RAG DevOps Assistant...")
    logger.info(f"Qdrant: {QDRANT_URL} / {QDRANT_COLLECTION}")
    logger.info(f"LLM: {LLM_MODEL}")

    embedder = Embedder()
    retriever = Retriever(QDRANT_URL, QDRANT_COLLECTION, embedder)
    generator = Generator(model=LLM_MODEL)

    # Verify Qdrant connection
    try:
        info = retriever.client.get_collection(QDRANT_COLLECTION)
        logger.info(f"Connected to Qdrant: {info.points_count} points in {QDRANT_COLLECTION}")
    except Exception as e:
        logger.warning(f"Qdrant connection failed (ingest first?): {e}")

    yield

    logger.info("Shutting down.")


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
    qdrant_points = 0
    if retriever:
        try:
            info = retriever.client.get_collection(QDRANT_COLLECTION)
            qdrant_points = info.points_count
        except Exception:
            pass

    return HealthResponse(
        status="ok",
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
    if not retriever or not generator:
        raise HTTPException(status_code=503, detail="Service not ready — models not loaded")

    t0 = time.monotonic()

    # Retrieve
    chunks = retriever.search(req.question, top_k=req.top_k)

    # Generate
    result = generator.generate(req.question, chunks)

    # Build sources
    sources = []
    if req.include_sources:
        for chunk in chunks:
            sources.append(SourceCitation(
                url=chunk.get("url", ""),
                title=chunk.get("title", "Unknown"),
                snippet=chunk["text"][:200] + ("..." if len(chunk["text"]) > 200 else ""),
            ))

    latency_ms = (time.monotonic() - t0) * 1000

    logger.info(f"Query complete: {latency_ms:.1f}ms, {result['tokens_used']} tokens, {len(sources)} sources")

    return QueryResponse(
        question=req.question,
        answer=result["answer"],
        sources=sources,
        tokens_used=result["tokens_used"],
        latency_ms=latency_ms,
        model=result["model"],
    )
