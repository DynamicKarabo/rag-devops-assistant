"""
Embedding generation using sentence-transformers.
Uses all-MiniLM-L6-v2 — 80MB, CPU-friendly, 384-dim vectors.
"""

import logging
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"


class Embedder:
    """Thin wrapper around SentenceTransformer with batching."""

    def __init__(self, model_name: str = MODEL_NAME):
        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        """
        Generate embeddings for a list of texts.
        Returns (N, dim) numpy float32 array.
        """
        logger.info(f"Embedding {len(texts)} texts (batch_size={batch_size})...")
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            normalize_embeddings=True,  # cosine similarity = dot product
        )
        return np.array(embeddings, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        """Generate embedding for a single query string."""
        embedding = self.model.encode(
            [query],
            normalize_embeddings=True,
        )
        return np.array(embedding, dtype=np.float32)[0]

    @property
    def dim(self) -> int:
        return self.model.get_sentence_embedding_dimension()
