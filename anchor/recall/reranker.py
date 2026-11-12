"""Multi-Way Score Reranker for Anchor Memory Recall.

Combines semantic, entity, emotion, and recency signals with
configurable weights into a composite score.

Threshold filter applies only to the Composite Score to reject irrelevant noise,
while DecayScore acts purely on final ranking to respect age and importance.
"""
import logging
from typing import List, Dict, Any, Optional

try:
    from anchor.config import (
        RECALL_WEIGHT_SEMANTIC,
        RECALL_WEIGHT_ENTITY,
        RECALL_WEIGHT_EMOTION,
        RECALL_WEIGHT_RECENCY,
        RECALL_TOP_K,
        RECALL_MIN_SCORE_THRESHOLD,
    )
except ImportError:
    from config import (
        RECALL_WEIGHT_SEMANTIC,
        RECALL_WEIGHT_ENTITY,
        RECALL_WEIGHT_EMOTION,
        RECALL_WEIGHT_RECENCY,
        RECALL_TOP_K,
        RECALL_MIN_SCORE_THRESHOLD,
    )

logger = logging.getLogger("anchor.recall.reranker")


class AnchorReranker:
    def __init__(
        self,
        w_semantic: float = RECALL_WEIGHT_SEMANTIC,
        w_entity: float = RECALL_WEIGHT_ENTITY,
        w_emotion: float = RECALL_WEIGHT_EMOTION,
        w_recency: float = RECALL_WEIGHT_RECENCY,
        top_k: int = RECALL_TOP_K,
        min_score: float = RECALL_MIN_SCORE_THRESHOLD,
    ):
        self.w_semantic = w_semantic
        self.w_entity = w_entity
        self.w_emotion = w_emotion
        self.w_recency = w_recency
        self.top_k = top_k
        self.min_score = min_score

    def rerank(
        self,
        active_memories: List[Dict[str, Any]],
        semantic_scores: Dict[str, float],
        entity_scores: Dict[str, float],
        emotion_scores: Dict[str, float],
        recency_scores: Dict[str, float],
        override_top_k: Optional[int] = None,
        query: str = "",
    ) -> List[Dict[str, Any]]:
        """Combine four retrieval signals into a final ranked list."""
        limit = override_top_k if override_top_k is not None else self.top_k

        # Detect historical cues in query
        q_lower = query.lower() if query else ""
        historical_cues = ["之前", "以前", "上一次", "那次", "过去", "记得那次", "小时候", "刚认识", "刚开始", "月", "去年", "暑假", "曾经"]
        is_historical = any(cue in q_lower for cue in historical_cues)

        w_sem = self.w_semantic + (self.w_recency if is_historical else 0.0)
        w_rec = 0.0 if is_historical else self.w_recency

        ranked_items = []
        for mem in active_memories:
            mem_id = mem["id"]
            sem = float(semantic_scores.get(mem_id, 0.0))
            ent = float(entity_scores.get(mem_id, 0.0))
            emo = float(emotion_scores.get(mem_id, 0.0))
            rec = float(recency_scores.get(mem_id, 0.0))

            composite = (
                w_sem * sem
                + self.w_entity * ent
                + self.w_emotion * emo
                + w_rec * rec
            )

            # High semantic similarity indicates direct historical retrieval interest;
            # neutralize decay penalty so older but highly relevant memories are retained.
            decay = float(mem.get("decay_score", 1.0))
            decay_eff = (0.95 + 0.05 * decay) if (is_historical or sem >= 0.35) else max(0.2, decay)
            final_score = composite * decay_eff
            if sem >= 0.35:
                final_score += (sem - 0.30) * 0.5

            # Noise filter: keep if composite/final meets threshold, or strong entity/semantic match
            if composite >= self.min_score or final_score >= self.min_score or ent >= 0.8 or sem >= 0.35:
                item_copy = dict(mem)
                item_copy["recall_score"] = round(final_score, 4)
                item_copy["composite_score"] = round(composite, 4)
                item_copy["_scores"] = {
                    "semantic": round(sem, 3),
                    "entity": round(ent, 3),
                    "emotion": round(emo, 3),
                    "recency": round(rec, 3),
                    "decay": round(decay, 3),
                }
                ranked_items.append(item_copy)

        ranked_items.sort(key=lambda x: x["recall_score"], reverse=True)
        top_results = ranked_items[:limit]

        logger.debug(f"Reranked {len(active_memories)} memories -> {len(top_results)} returned (top_k={limit})")
        return top_results
