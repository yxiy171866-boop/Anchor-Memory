"""Multi-Way Memory Retriever for Anchor.

Provides four independent retrieval signals:
1. Semantic similarity (embedding cosine)
2. Entity/keyword overlap
3. Emotional coordinate proximity (valence + arousal distance)
4. Recency score (exponential decay on age)
"""
import json
import logging
import math
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    from anchor.recall.embedder import AnchorEmbedder
    from anchor.db.connection import get_db
    from anchor.config import RECALL_MIN_SCORE_THRESHOLD
except ImportError:
    from recall.embedder import AnchorEmbedder
    from db.connection import get_db
    from config import RECALL_MIN_SCORE_THRESHOLD

logger = logging.getLogger("anchor.recall.retriever")


class MultiWayRetriever:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.embedder = AnchorEmbedder(db_path=db_path)

    def _db(self):
        if self.db_path:
            return get_db(self.db_path)
        return get_db()

    def fetch_active_memories(self) -> List[Dict[str, Any]]:
        """Fetch all active memories as plain dicts for retrieval processing."""
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, content, category, importance, valence, arousal,
                       emotion_label, entities, decay_score, created_at, last_accessed_at
                FROM anchor_memories
                WHERE status = 'active'
                ORDER BY decay_score DESC
                """
            )
            rows = cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                try:
                    d["entities"] = json.loads(d.get("entities") or "[]")
                except Exception:
                    d["entities"] = []
                result.append(d)
            return result

    def retrieve_by_semantic(self, query: str, memories: List[Dict[str, Any]]) -> Dict[str, float]:
        """Compute cosine similarity between query embedding and each memory's embedding."""
        if not query or not memories:
            return {}

        query_vec = self.embedder.get_embedding(query)
        scores = {}
        for mem in memories:
            mem_vec = self.embedder.get_cached_embedding(mem["id"], mem["content"])
            scores[mem["id"]] = self.embedder.cosine_similarity(query_vec, mem_vec)
        return scores

    def retrieve_by_entity(self, query: str, memories: List[Dict[str, Any]]) -> Dict[str, float]:
        """Score memories by entity/keyword overlap with query."""
        if not query or not memories:
            return {}

        entities = self.extract_entities(query)
        query_words = set(query.lower().split())
        scores = {}

        for mem in memories:
            mem_entities = set(e.lower() for e in (mem.get("entities") or []))
            mem_words = set(mem["content"].lower().split())

            entity_overlap = len(entities & mem_entities)
            word_overlap = len(query_words & mem_words)

            # Normalize
            max_possible = max(1, len(entities) + len(query_words))
            score = min(1.0, (entity_overlap * 2 + word_overlap) / max_possible)
            scores[mem["id"]] = score
        return scores

    def retrieve_by_emotion(
        self,
        query: str,
        memories: List[Dict[str, Any]],
        detected_valence: Optional[float] = None,
        detected_arousal: Optional[float] = None,
        detected_label: Optional[str] = None
    ) -> Dict[str, float]:
        """Score memories by proximity in emotional coordinate space."""
        if not memories:
            return {}

        # Use provided emotional coords or fall back to neutral
        q_val = float(detected_valence) if detected_valence is not None else 0.0
        q_aro = float(detected_arousal) if detected_arousal is not None else 0.0

        scores = {}
        for mem in memories:
            m_val = float(mem.get("valence") or 0.0)
            m_aro = float(mem.get("arousal") or 0.0)

            # Euclidean distance in 2D emotion space; max distance = sqrt(2*4) = ~2.83
            dist = math.sqrt((q_val - m_val) ** 2 + (q_aro - m_aro) ** 2)
            score = max(0.0, 1.0 - dist / 2.83)

            # Boost if emotion label matches
            if detected_label and detected_label == mem.get("emotion_label"):
                score = min(1.0, score + 0.2)

            scores[mem["id"]] = score
        return scores

    def retrieve_by_recency(self, memories: List[Dict[str, Any]]) -> Dict[str, float]:
        """Score memories by how recently they were accessed or created."""
        if not memories:
            return {}

        now = datetime.now()
        scores = {}
        for mem in memories:
            ts_str = mem.get("last_accessed_at") or mem.get("created_at") or ""
            try:
                ts = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
                days_ago = (now - ts).total_seconds() / 86400
                # Exponential decay with 30-day half-life
                score = math.exp(-days_ago / 30.0)
            except Exception:
                score = 0.0
            scores[mem["id"]] = score
        return scores

    def extract_entities(self, text: str) -> set:
        """Extract potential entity mentions from text using simple heuristics."""
        words = set()
        for word in text.split():
            clean = word.strip("，。！？,.!?\"'""''()（）[]【】").strip()
            if len(clean) >= 2:
                words.add(clean.lower())
        return words
