"""Anchor Midnight Step 2 - Long-Term Memory Extraction & Emotional Coordinate Tagging.

Extracts facts, episodic events, and preferences from daily dialogue,
attaching valence, arousal, emotion labels, and entities.
"""
import logging
from typing import List, Dict, Any, Optional

try:
    from anchor.config import ANCHOR_DB_PATH
    from anchor.long_term.service import LongTermMemoryService
    from anchor.long_term.backfill_service import AnchorBackfillService
    from anchor.models.memory_item import MemoryItem
except ImportError:
    from config import ANCHOR_DB_PATH
    from long_term.service import LongTermMemoryService
    from long_term.backfill_service import AnchorBackfillService
    from models.memory_item import MemoryItem

logger = logging.getLogger("anchor.midnight.extractor")


class MemoryExtractor:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or ANCHOR_DB_PATH
        self.lt_service = LongTermMemoryService(db_path=self.db_path)
        self.backfill_service = AnchorBackfillService(db_path=self.db_path)

    def extract_and_store_memories(
        self,
        candidate_items: List[Dict[str, Any]],
        date_str: str
    ) -> List[MemoryItem]:
        """Extract and persist long-term memories with heuristic emotional tagging.
        
        candidate_items: list of dicts with keys: content, category, importance,
                         optionally valence, arousal, emotion_label, entities
        """
        created_memories = []

        for item in candidate_items:
            content = item.get("content", "").strip()
            if not content:
                continue

            category = item.get("category", "episodic")
            importance = float(item.get("importance", 0.6))

            # Deduce or inherit valence/arousal/emotion
            val = item.get("valence")
            aro = item.get("arousal")
            emo = item.get("emotion_label")

            if val is None or aro is None or not emo:
                h_val, h_aro, h_emo = self.backfill_service.heuristic_emotion_estimate(content)
                val = val if val is not None else h_val
                aro = aro if aro is not None else h_aro
                emo = emo or h_emo

            entities = item.get("entities")
            if not entities:
                entities = self.backfill_service.extract_entities(content)

            mem = self.lt_service.create_memory(
                content=content,
                category=category,
                importance=importance,
                valence=float(val),
                arousal=float(aro),
                emotion_label=emo,
                entities=entities,
            )
            created_memories.append(mem)
            logger.info(f"Extracted memory [{mem.id}]: {content[:40]}...")

        return created_memories
