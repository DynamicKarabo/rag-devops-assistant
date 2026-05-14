"""
Ingestion pipeline entry point.
Usage: python -m ingest.pipeline --source k8s --source docker
"""

import argparse
import logging
from ingest.crawler import crawl_docs
from ingest.chunker import chunk_documents
from ingest.embedder import Embedder
from ingest.indexer import Indexer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SOURCES = {
    "k8s": {
        "name": "Kubernetes",
        "base_url": "https://kubernetes.io/docs/",
        "sitemap": "https://kubernetes.io/sitemap.xml",
    },
    "docker": {
        "name": "Docker",
        "base_url": "https://docs.docker.com/",
        "sitemap": "https://docs.docker.com/sitemap.xml",
    },
    "terraform": {
        "name": "Terraform",
        "base_url": "https://developer.hashicorp.com/terraform/",
        "sitemap": None,  # crawl from index
    },
}


def main():
    parser = argparse.ArgumentParser(description="Ingest DevOps docs into Qdrant")
    parser.add_argument("--source", action="append", choices=list(SOURCES),
                        help="Doc sources to ingest (repeatable)")
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--collection", default="devops_docs")
    parser.add_argument("--chunk-size", type=int, default=512)
    parser.add_argument("--chunk-overlap", type=int, default=64)
    parser.add_argument("--limit", type=int, default=200,
                        help="Max pages per source (for initial ingest)")
    args = parser.parse_args()

    sources = args.source or list(SOURCES.keys())
    logger.info(f"Ingesting sources: {sources}")

    # 1. Crawl
    all_docs = []
    for src_key in sources:
        cfg = SOURCES[src_key]
        logger.info(f"Crawling {cfg['name']}...")
        docs = crawl_docs(cfg, limit=args.limit)
        logger.info(f"  → {len(docs)} pages")
        all_docs.extend(docs)

    if not all_docs:
        logger.error("No documents crawled. Aborting.")
        return

    # 2. Chunk
    logger.info(f"Chunking {len(all_docs)} documents...")
    chunks = chunk_documents(all_docs, chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    logger.info(f"  → {len(chunks)} chunks")

    # 3. Embed
    logger.info("Generating embeddings...")
    embedder = Embedder()
    texts = [c["text"] for c in chunks]
    vectors = embedder.embed_batch(texts)
    logger.info(f"  → {len(vectors)} vectors ({vectors.shape[1]}-dim)")

    # 4. Index
    logger.info(f"Indexing into Qdrant ({args.qdrant_url}, collection={args.collection})...")
    indexer = Indexer(args.qdrant_url, args.collection)
    indexer.create_collection(vector_size=vectors.shape[1])
    indexer.upsert_chunks(chunks, vectors)
    logger.info("Done. Ingest complete.")


if __name__ == "__main__":
    main()
