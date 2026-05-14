"""
Qdrant indexer — creates collection and upserts chunks with vectors.
"""

import logging
import uuid
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    SparseVectorParams,
)

logger = logging.getLogger(__name__)


class Indexer:
    """Manages Qdrant collection lifecycle and upserts."""

    def __init__(self, url: str = "http://localhost:6333", collection: str = "devops_docs"):
        self.client = QdrantClient(url=url)
        self.collection = collection

    def create_collection(self, vector_size: int, force_recreate: bool = False):
        """Create collection if it doesn't exist."""
        collections = [c.name for c in self.client.get_collections().collections]

        if self.collection in collections:
            if force_recreate:
                logger.info(f"Recreating collection: {self.collection}")
                self.client.delete_collection(self.collection)
            else:
                logger.info(f"Collection {self.collection} already exists")
                return

        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"Created collection: {self.collection} (dim={vector_size})")

    def upsert_chunks(self, chunks: list[dict], vectors: "np.ndarray", batch_size: int = 100):
        """
        Upsert chunks with their vectors into Qdrant.
        Each chunk gets a UUID point ID.
        """
        points = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            point_id = str(uuid.uuid4())
            payload = {
                "text": chunk["text"],
                "url": chunk.get("url", ""),
                "title": chunk.get("title", ""),
                "source": chunk.get("source", ""),
                "chunk_index": chunk.get("chunk_index", 0),
            }
            points.append(PointStruct(id=point_id, vector=vector.tolist(), payload=payload))

        total = len(points)
        for start in range(0, total, batch_size):
            batch = points[start : start + batch_size]
            self.client.upsert(collection_name=self.collection, points=batch)
            logger.info(f"  Upserted {min(start + batch_size, total)}/{total} points")

        logger.info(f"Upsert complete: {total} points in {self.collection}")

    def collection_info(self) -> dict:
        """Return collection stats."""
        info = self.client.get_collection(self.collection)
        return {
            "name": self.collection,
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "status": info.status,
        }
