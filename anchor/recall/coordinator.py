"""Unified Recall Coordinator for Anchor Memory System."""
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    from anchor.db.connection import get_db
    from anchor.recall.multi_retriever import MultiWayRetriever
    from anchor.recall.reranker import AnchorReranker
except ImportError:
    from db.connection import get_db
    from recall.multi_retriever import MultiWayRetriever
    from recall.reranker import AnchorReranker

logger = logging.getLogger("anchor.recall")


class AnchorRecallCoordinator:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.retriever = MultiWayRetriever(db_path=db_path)
        self.reranker = AnchorReranker()

    def _db(self):
        if self.db_path:
            return get_db(self.db_path)
        return get_db()

    def recall(
        self,
        query: str,
        top_k: Optional[int] = None,
        detected_valence: Optional[float] = None,
        detected_arousal: Optional[float] = None,
        detected_label: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Execute 4-path retrieval and reranking for the given query."""
        if not query or not query.strip():
            return []

        active_memories = self.retriever.fetch_active_memories()
        if not active_memories:
            return []

        # Run 4 retrieval paths
        s_sem = self.retriever.retrieve_by_semantic(query, active_memories)
        s_ent = self.retriever.retrieve_by_entity(query, active_memories)
        s_emo = self.retriever.retrieve_by_emotion(
            query, active_memories, detected_valence, detected_arousal, detected_label
        )
        s_rec = self.retriever.retrieve_by_recency(active_memories)

        # Rerank
        results = self.reranker.rerank(
            active_memories=active_memories,
            semantic_scores=s_sem,
            entity_scores=s_ent,
            emotion_scores=s_emo,
            recency_scores=s_rec,
            override_top_k=top_k
        )

        # Reinforce recalled memories by updating last_accessed_at
        if results:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            recalled_ids = [r["id"] for r in results]
            placeholders = ",".join(["?"] * len(recalled_ids))
            try:
                with self._db() as conn:
                    conn.execute(
                        f"UPDATE anchor_memories SET last_accessed_at = ? WHERE id IN ({placeholders})",
                        [now] + recalled_ids
                    )
            except Exception as e:
                logger.debug(f"Failed to touch last_accessed_at: {e}")

        return results
