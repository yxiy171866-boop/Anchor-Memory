"""Legacy Memory Backfill and Emotion Inference Service for Anchor.

Safely reads existing legacy memories (read-only from legacy DB),
infers missing emotional coordinates (valence, arousal, emotion_label),
and populates the isolated anchor_memories table without modifying legacy data.

This module is OPTIONAL. It is only needed if you are migrating from an older
memory database format. Configure LEGACY_DB_PATH to point to your old database.
"""
import sqlite3
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    from anchor.db.connection import get_db
    from anchor.long_term.service import LongTermMemoryService
except ImportError:
    from db.connection import get_db
    from long_term.service import LongTermMemoryService

logger = logging.getLogger("anchor.backfill")

# Rule-based sentiment heuristic for fast offline enrichment.
# Evaluated in priority order. Customize these keywords for your use case.
EMOTION_HEURISTICS = [
    (["favorite", "prefer", "like", "dislike", "habit", "usually"], 0.2, 0.2, "preference"),
    (["sick", "pain", "fever", "hospital", "medicine", "hurt", "nightmare"], -0.4, 0.7, "care"),
    (["sad", "cry", "tired", "exhausted", "stressed", "anxious", "overwhelmed"], -0.7, 0.8, "comfort"),
    (["wedding", "together", "promise", "forever", "love", "happy", "hug", "dear"], 0.9, 0.8, "joy"),
    (["work", "code", "system", "feature", "fix", "update"], 0.3, 0.4, "productivity"),
]


def infer_emotion_coordinates(content: str, existing_label: str = "", existing_val: float = 0.0, existing_aro: float = 0.0):
    """Infer valence, arousal, and emotion_label from memory content if missing."""
    if existing_label and existing_label.strip() and (existing_val != 0.0 or existing_aro != 0.0):
        return existing_val, existing_aro, existing_label.strip()

    text = content.lower()
    for keywords, val, aro, label in EMOTION_HEURISTICS:
        if any(kw in text for kw in keywords):
            return val, aro, label

    return 0.0, 0.1, "general"


class LegacyMemoryBackfillService:
    def __init__(
        self,
        anchor_db_path: Optional[str] = None,
        legacy_db_path: str = "data/legacy_memories.db",
        db_path: Optional[str] = None
    ):
        self.anchor_db_path = db_path or anchor_db_path
        self.legacy_db_path = legacy_db_path
        self.lt_service = LongTermMemoryService(db_path=self.anchor_db_path)

    def heuristic_emotion_estimate(self, content: str):
        """Estimate valence, arousal, emotion_label from text."""
        return infer_emotion_coordinates(content)

    def extract_entities(self, content: str) -> List[str]:
        """Extract key noun entities from text using simple heuristics."""
        try:
            from anchor.recall.multi_retriever import MultiWayRetriever
            retriever = MultiWayRetriever(db_path=self.anchor_db_path)
            return retriever.extract_entities(content)
        except Exception:
            return []

    def run_backfill(self, max_items: Optional[int] = None) -> Dict[str, Any]:
        """Perform non-destructive migration into anchor_memories with backfilled=1.

        Expects legacy DB to have a 'memories' table with columns:
        id, content, category, importance, valence, arousal, emotion_label, created_at
        """
        try:
            with sqlite3.connect(self.legacy_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                query = "SELECT * FROM memories WHERE deleted = 0 ORDER BY id ASC"
                if max_items:
                    query += f" LIMIT {int(max_items)}"
                cursor.execute(query)
                legacy_rows = cursor.fetchall()
        except Exception as e:
            logger.error(f"Failed to read legacy DB: {e}")
            return {"success": False, "error": str(e)}

        migrated_count = 0
        skipped_count = 0

        for r in legacy_rows:
            anchor_id = f"mem_legacy_{r['id']}"
            existing = self.lt_service.get_memory(anchor_id)
            if existing:
                skipped_count += 1
                continue

            val, aro, label = infer_emotion_coordinates(
                r["content"],
                r["emotion_label"] or "",
                float(r["valence"] or 0.0),
                float(r["arousal"] or 0.0)
            )

            # Map legacy importance (1-5 int scale) to 0.0-1.0 float
            raw_imp = float(r["importance"] or 1)
            importance = min(1.0, max(0.1, raw_imp / 5.0)) if raw_imp > 1.0 else 0.5
            is_pinned = r["pinned"] if "pinned" in r.keys() else 0
            if is_pinned == 1:
                importance = 0.9  # Pinned memories treated as core memories

            self.lt_service.create_memory(
                content=r["content"],
                category=r["category"] or "general",
                importance=importance,
                valence=val,
                arousal=aro,
                emotion_label=label,
                entities=[],
                links=[],
                custom_id=anchor_id,
                created_at=r["created_at"],
                backfilled=1
            )
            migrated_count += 1

        logger.info(f"Backfill complete: {migrated_count} migrated, {skipped_count} skipped.")
        return {
            "success": True,
            "migrated_count": migrated_count,
            "skipped_count": skipped_count,
            "total_legacy": len(legacy_rows),
        }

    def backfill_batch(self, limit: int = 10) -> dict:
        """Batch backfill alias for scheduled nightly pipeline."""
        return self.run_backfill(max_items=limit)


# Alias for backward compatibility
AnchorBackfillService = LegacyMemoryBackfillService
