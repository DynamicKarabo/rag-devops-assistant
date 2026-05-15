"""
Custom Prometheus metrics for RAG observability.
Latency histograms, token counters, cost tracking.
"""

from prometheus_client import Histogram, Counter, Gauge

# Query latency broken down by component
rag_query_latency = Histogram(
    "rag_query_latency_seconds",
    "Total query latency (retrieval + generation)",
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 40.0, 60.0, 120.0),
)

rag_retrieval_latency = Histogram(
    "rag_retrieval_latency_seconds",
    "Qdrant retrieval latency",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

rag_llm_latency = Histogram(
    "rag_llm_latency_seconds",
    "LLM API call latency",
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 40.0, 60.0, 120.0),
)

# Tokens and sources
rag_tokens_total = Counter(
    "rag_tokens_total",
    "Total tokens consumed by LLM calls",
)

rag_sources_per_query = Histogram(
    "rag_sources_per_query",
    "Number of source documents returned per query",
    buckets=(0, 1, 2, 3, 5, 8, 10),
)

# Cost estimation
rag_cost_total = Counter(
    "rag_cost_total",
    "Estimated total cost of LLM calls (USD)",
)

# Qdrant health
rag_qdrant_points = Gauge(
    "rag_qdrant_points",
    "Number of points in Qdrant collection",
)

rag_qdrant_up = Gauge(
    "rag_qdrant_up",
    "Whether Qdrant is reachable (1=up, 0=down)",
)

# Query errors by type
rag_errors_total = Counter(
    "rag_errors_total",
    "Query errors by type",
    labelnames=("error_type",),
)
