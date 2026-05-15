#!/usr/bin/env python3
"""
Retrieval-quality evaluation for RAG DevOps Assistant.
Zero LLM calls — uses local embeddings + domain heuristics.
Scores retrieval precision. Works on OpenRouter free tier.

Exit code 0 = gates passed. Exit code 1 = failed.
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx
from sentence_transformers import SentenceTransformer

# ── Config ──
API_URL = os.getenv("RAG_API_URL", "http://localhost:8000")
BENCHMARK_PATH = Path(__file__).parent / "benchmark.json"

# Map question domains to expected URL patterns
DOMAIN_PATTERNS = {
    "kubernetes": "kubernetes.io",
    "docker": "docs.docker.com",
    "terraform": "terraform.io",
}

# Quality gates
RETRIEVAL_PRECISION_GATE = 0.5  # 50% of sources must be domain-relevant
RETRIEVAL_SIMILARITY_GATE = 0.3  # avg cosine similarity threshold
LATENCY_P99_GATE_MS = 60_000    # p99 latency < 60s


def load_benchmark() -> list[dict]:
    with open(BENCHMARK_PATH) as f:
        return json.load(f)["items"]


def guess_domain(question: str) -> str | None:
    """Guess the expected domain from the question text."""
    q = question.lower()
    if any(kw in q for kw in ["kubernetes", "k8s", "kubectl", "pod", "deployment", "configmap", "namespace"]):
        return "kubernetes"
    if any(kw in q for kw in ["docker", "container", "compose", "swarm"]):
        return "docker"
    if any(kw in q for kw in ["terraform", "hcl", "state file"]):
        return "terraform"
    return None


def source_matches_domain(source: dict, domain: str) -> bool:
    """Check if a source URL matches the expected domain."""
    url = source.get("url", "").lower()
    expected = DOMAIN_PATTERNS.get(domain, "")
    return expected in url


def query_rag(question: str, top_k: int = 3, retries: int = 2) -> dict:
    """Call the RAG API with retries on connection errors."""
    for attempt in range(retries + 1):
        try:
            resp = httpx.post(
                f"{API_URL}/query",
                json={"question": question, "include_sources": True, "top_k": top_k},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError:
            if attempt < retries:
                time.sleep(3)
            else:
                return {"answer": "ERROR: Connection refused after retries", "sources": []}
        except Exception as e:
            return {"answer": f"ERROR: {e}", "sources": []}
    return {"answer": "ERROR", "sources": []}


def run_eval() -> dict:
    """Run retrieval evaluation on all benchmark items."""
    items = load_benchmark()
    print(f"📋 Loaded {len(items)} benchmark questions\n")

    # Load local embedding model (no API call needed)
    embedder = SentenceTransformer("all-MiniLM-L6-v2")

    results = {
        "total": len(items),
        "successful": 0,
        "failed": 0,
        "precision_scores": [],
        "similarity_scores": [],
        "latencies_ms": [],
        "tokens": [],
        "source_counts": [],
        "per_item": {},
    }

    for i, item in enumerate(items):
        qid = item["id"]
        question = item["question"]
        print(f"[{i+1}/{len(items)}] {qid}: {question[:80]}...", end=" ", flush=True)

        start = time.monotonic()
        result = query_rag(question)
        elapsed_ms = (time.monotonic() - start) * 1000

        answer = result.get("answer", "")
        sources = result.get("sources", [])
        tokens = result.get("tokens_used", 0)

        if answer.startswith("ERROR"):
            print(f"❌ {answer.split(':')[1] if ':' in answer else answer}")
            results["failed"] += 1
            results["per_item"][qid] = {"status": "error", "error": answer}
            continue

        # ── Retrieval precision: do sources match question domain? ──
        domain = guess_domain(question)
        if domain and sources:
            matches = sum(1 for s in sources if source_matches_domain(s, domain))
            precision = matches / len(sources)
        elif sources:
            precision = 0.5  # neutral if domain guess failed
        else:
            precision = 0.0

        # ── Semantic similarity: question vs source snippets ──
        if sources:
            snippets = [s.get("snippet", "") for s in sources]
            q_emb = embedder.encode(question)
            s_embs = embedder.encode(snippets)
            similarities = embedder.similarity(q_emb, s_embs).flatten().tolist()
            avg_sim = sum(similarities) / len(similarities)
        else:
            similarities = []
            avg_sim = 0.0

        results["successful"] += 1
        results["precision_scores"].append(precision)
        results["similarity_scores"].append(avg_sim)
        results["latencies_ms"].append(elapsed_ms)
        results["tokens"].append(tokens)
        results["source_counts"].append(len(sources))

        results["per_item"][qid] = {
            "status": "ok",
            "precision": round(precision, 3),
            "avg_similarity": round(avg_sim, 3),
            "latency_ms": round(elapsed_ms, 0),
            "tokens": tokens,
            "sources": len(sources),
            "top_similarity": round(max(similarities), 3) if similarities else 0,
        }

        status = "✅" if precision >= RETRIEVAL_PRECISION_GATE else "⚠️"
        print(f"{status} prec={precision:.2f} sim={avg_sim:.3f} {elapsed_ms:.0f}ms")

    return results


def print_report(results: dict):
    """Print evaluation report."""
    print("\n" + "=" * 60)
    print("📊 RETRIEVAL EVALUATION REPORT")
    print("=" * 60)

    n = results["successful"]
    total = results["total"]
    print(f"\nQueries: {n}/{total} successful ({results['failed']} failed)")

    if n == 0:
        print("\n❌ No successful queries — cannot compute scores.")
        return

    precisions = results["precision_scores"]
    similarities = results["similarity_scores"]
    latencies = results["latencies_ms"]
    tokens_list = results["tokens"]
    sources_list = results["source_counts"]

    avg_precision = sum(precisions) / len(precisions)
    avg_similarity = sum(similarities) / len(similarities)
    avg_latency = sum(latencies) / len(latencies)
    sorted_lat = sorted(latencies)
    p95_latency = sorted_lat[int(len(sorted_lat) * 0.95)] if sorted_lat else 0
    p99_latency = sorted_lat[int(len(sorted_lat) * 0.99)] if sorted_lat else 0
    total_tokens = sum(tokens_list)
    avg_sources = sum(sources_list) / len(sources_list) if sources_list else 0

    # Gate checks
    precision_pass = avg_precision >= RETRIEVAL_PRECISION_GATE
    similarity_pass = avg_similarity >= RETRIEVAL_SIMILARITY_GATE
    latency_pass = p99_latency <= LATENCY_P99_GATE_MS

    print("\nAggregate Scores:")
    print("-" * 40)
    print(f"  {'✅' if precision_pass else '❌'} Retrieval Precision:    {avg_precision:.3f}  (gate: ≥{RETRIEVAL_PRECISION_GATE})")
    print(f"  {'✅' if similarity_pass else '❌'} Semantic Similarity:    {avg_similarity:.3f}  (gate: ≥{RETRIEVAL_SIMILARITY_GATE})")
    print(f"  {'✅' if latency_pass else '❌'} Latency p99:            {p99_latency:.0f}ms  (gate: ≤{LATENCY_P99_GATE_MS}ms)")
    print(f"\n  Avg Latency:           {avg_latency:.0f}ms")
    print(f"  Latency p95:           {p95_latency:.0f}ms")
    print(f"  Total Tokens:          {total_tokens}")
    print(f"  Avg Sources/Query:     {avg_sources:.1f}")

    print("\nPer-Question Detail:")
    print("-" * 60)
    for qid, info in results["per_item"].items():
        if info["status"] == "error":
            print(f"  ❌ {qid}: {info.get('error', 'unknown')[:80]}")
        else:
            prec = info["precision"]
            sim = info["avg_similarity"]
            lat = info["latency_ms"]
            pflag = "✅" if prec >= RETRIEVAL_PRECISION_GATE else "⚠️"
            print(f"  {pflag} {qid}: prec={prec:.2f} sim={sim:.3f} lat={lat:.0f}ms")

    all_pass = precision_pass and similarity_pass and latency_pass
    print(f"\n{'✅ ALL GATES PASSED' if all_pass else '❌ SOME GATES FAILED'}")


if __name__ == "__main__":
    results = run_eval()
    print_report(results)

    # Exit code based on gates
    n = results["successful"]
    if n == 0:
        sys.exit(1)

    avg_prec = sum(results["precision_scores"]) / n
    avg_sim = sum(results["similarity_scores"]) / n
    lats = sorted(results["latencies_ms"])
    p99 = lats[int(len(lats) * 0.99)] if lats else 0

    passed = (
        avg_prec >= RETRIEVAL_PRECISION_GATE
        and avg_sim >= RETRIEVAL_SIMILARITY_GATE
        and p99 <= LATENCY_P99_GATE_MS
    )
    sys.exit(0 if passed else 1)
