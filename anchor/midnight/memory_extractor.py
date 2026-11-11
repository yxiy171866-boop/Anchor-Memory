"""Anchor Midnight Step 2 - Long-Term Memory Extraction with Provenance.

Extracts facts, episodic events, and preferences from daily dialogue,
attaching valence, arousal, emotion labels, provenance tracking, and entity lists.
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
        """Extract and persist long-term memories with heuristic emotional tagging and source tracking.

        Guarantees that entities is converted from set to list before insertion.
        """
        created_memories = []

        for item in candidate_items:
            content = item.get("content", "").strip()
            if not content:
                continue

            category = item.get("category", "episodic")
            raw_importance = item.get("importance")
            importance = 0.6 if raw_importance is None else max(0.0, min(1.0, float(raw_importance)))

            # Deduce or inherit valence/arousal/emotion
            val = item.get("valence")
            aro = item.get("arousal")
            emo = item.get("emotion_label")

            if val is None or aro is None or not emo:
                h_val, h_aro, h_emo = self.backfill_service.heuristic_emotion_estimate(content)
                val = val if val is not None else h_val
                aro = aro if aro is not None else h_aro
                emo = emo or h_emo

            # Convert entities to list (resolves TypeError when set is returned)
            entities = item.get("entities")
            if not entities:
                entities = self.backfill_service.extract_entities(content)
            if isinstance(entities, set):
                entities = list(entities)

            is_protected = int(item.get("is_protected", 0))
            source_msg_id = str(item.get("source_message_id", "")) if item.get("source_message_id") else None
            confidence = float(item.get("confidence", 1.0))

            mem = self.lt_service.create_memory(
                content=content,
                category=category,
                importance=importance,
                valence=float(val),
                arousal=float(aro),
                emotion_label=emo,
                entities=entities,
                is_protected=is_protected,
                source_message_id=source_msg_id,
                source_date=date_str,
                confidence=confidence
            )
            created_memories.append(mem)
            logger.info(f"Extracted memory [{mem.id}]: {content[:40]}... (provenance={source_msg_id})")

        return created_memories
