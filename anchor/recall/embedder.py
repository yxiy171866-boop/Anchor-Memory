"""Anchor Embedding and Vector Similarity Service.

Provides resilient embedding generation with automatic local fallback,
dimension and model metadata tracking, and cosine similarity computation.
"""
import math
import json
import hashlib
import logging
from typing import List, Optional

try:
    from anchor.db.connection import get_db
except ImportError:
    from db.connection import get_db

logger = logging.getLogger("anchor.embedder")

FALLBACK_DIMENSION = 64
FALLBACK_MODEL = "local_ngram_v1"


def _local_fallback_vector(text: str, dim: int = FALLBACK_DIMENSION) -> List[float]:
    """Generate a deterministic unit-normalized dense vector using character n-grams.

    Guarantees that similar texts share high cosine similarity even when
    network/API is completely offline.
    """
    clean_text = (text or "").strip().lower()
    if not clean_text:
        return [0.0] * dim

    vec = [0.0] * dim
    ngrams = []
    for n in (2, 3):
        for i in range(max(0, len(clean_text) - n + 1)):
            ngrams.append(clean_text[i:i + n])

    if not ngrams:
        ngrams = list(clean_text)

    for gram in ngrams:
        h = int(hashlib.md5(gram.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if ((h >> 8) & 1) == 1 else -1.0
        vec[idx] += sign

    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


class AnchorEmbedder:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def _db(self):
        if self.db_path:
            return get_db(self.db_path)
        return get_db()

    def get_embedding(self, text: str) -> tuple[List[float], str, int]:
        """Obtain embedding vector, model identifier, and dimension for given text."""
        clean_text = (text or "").strip()
        if not clean_text:
            return [0.0] * FALLBACK_DIMENSION, FALLBACK_MODEL, FALLBACK_DIMENSION

        # Attempt to use configured external embedding service
        try:
            import os
            import urllib.request
            api_url = os.getenv("ANCHOR_EMBEDDING_API_URL", "")
            if api_url:
                payload = json.dumps({"text": clean_text}).encode("utf-8")
                req = urllib.request.Request(
                    api_url, data=payload, headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    result = json.loads(resp.read())
                    vector = result.get("embedding") or result.get("vector")
                    model = result.get("model", "external_api")
                    if vector and isinstance(vector, list) and len(vector) > 0:
                        dim = len(vector)
                        return [float(x) for x in vector], model, dim
        except Exception as e:
            logger.debug(f"External embedding service unavailable, using local fallback: {e}")

        # Local deterministic fallback
        return _local_fallback_vector(clean_text), FALLBACK_MODEL, FALLBACK_DIMENSION

    def get_embedding_vector(self, text: str) -> List[float]:
        """Convenience method returning vector only."""
        vec, _, _ = self.get_embedding(text)
        return vec

    def cache_memory_embedding(self, memory_id: str, content: str) -> List[float]:
        """Compute and persist embedding for a memory item with dimension verification."""
        content_hash = hashlib.sha256(content.strip().encode("utf-8")).hexdigest()
        vector, model, dim = self.get_embedding(content)
        vector_json = json.dumps(vector)

        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO anchor_embeddings
                (memory_id, content_hash, embedding_model, dimension, vector_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (memory_id, content_hash, model, dim, vector_json)
            )
        return vector

    def get_cached_embedding(self, memory_id: str, content: str) -> List[float]:
        """Retrieve cached embedding if valid and matching active model dimension, or recompute."""
        content_hash = hashlib.sha256(content.strip().encode("utf-8")).hexdigest()
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT vector_json, content_hash, dimension FROM anchor_embeddings WHERE memory_id = ?",
                (memory_id,)
            )
            row = cursor.fetchone()
            if row and row["content_hash"] == content_hash:
                try:
                    loaded = json.loads(row["vector_json"])
                    if len(loaded) == (row["dimension"] or len(loaded)):
                        return loaded
                except Exception:
                    pass

        return self.cache_memory_embedding(memory_id, content)

    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0

        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))

        if norm1 <= 0.0 or norm2 <= 0.0:
            return 0.0

        sim = dot / (norm1 * norm2)
        return max(0.0, min(1.0, float(sim)))
