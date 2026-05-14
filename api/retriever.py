"""
Hybrid retriever — searches Qdrant for relevant chunks.
"""

import logging
from qdrant_client import QdrantClient

from ingest.embedder import Embedder

logger = logging.getLogger(__name__)


class Retriever:
    """Searches Qdrant with dense embeddings."""

    def __init__(self, qdrant_url: str, collection: str, embedder: Embedder):
        self.client = QdrantClient(url=qdrant_url)
        self.collection = collection
        self.embedder = embedder

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Search Qdrant for chunks relevant to the query.
        Returns list of {"text": str, "url": str, "title": str, "score": float}
        """
        query_vector = self.embedder.embed_query(query)

        results = self.client.query_points(
            collection_name=self.collection,
            query=query_vector.tolist(),
            limit=top_k,
            with_payload=True,
        )

        chunks = []
        for hit in results.points:
            payload = hit.payload or {}
            chunks.append({
                "text": payload.get("text", ""),
                "url": payload.get("url", ""),
                "title": payload.get("title", ""),
                "source": payload.get("source", ""),
                "score": hit.score or 0.0,
            })

        logger.info(f"Retrieved {len(chunks)} chunks for query (top score: {chunks[0]['score']:.3f})" if chunks else "No chunks retrieved")
        return chunks
