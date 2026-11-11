"""Legacy Memory Backfill and Emotion Inference Service for Anchor.

Safely reads existing legacy memories with non-duplicating ID offset tracking,
infers missing emotional coordinates (valence, arousal, emotion_label),
and gracefully skips when legacy database is absent without creating empty files.
"""
import os
import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    from anchor.db.connection import get_db
    from anchor.long_term.service import LongTermMemoryService
except ImportError:
    from db.connection import get_db
    from long_term.service import LongTermMemoryService

logger = logging.getLogger("anchor.backfill")

# Rule-based sentiment heuristic for fast offline enrichment (supporting Chinese and English)
EMOTION_HEURISTICS = [
    (["喜欢", "爱吃", "口味", "偏好", "习惯", "喝水", "咖啡", "奶茶", "吃辣", "favorite", "prefer", "like", "dislike"], 0.3, 0.2, "生活偏好"),
    (["生病", "感冒", "发烧", "肚子疼", "头疼", "医院", "吃药", "难受", "噩梦", "害怕", "sick", "pain", "fever", "hospital", "medicine"], -0.4, 0.7, "身体关怀"),
    (["难过", "哭了", "累", "疲惫", "压力", "焦虑", "烦躁", "崩溃", "委屈", "sad", "cry", "tired", "stressed", "anxious"], -0.7, 0.8, "情绪抚慰"),
    (["结婚", "戒指", "初遇", "相识", "约定", "开心", "爱", "陪伴", "永远", "wedding", "together", "promise", "forever", "love"], 0.9, 0.8, "甜蜜感动"),
    (["工作", "代码", "项目", "系统", "功能", "修复", "更新", "work", "code", "system", "feature", "fix"], 0.2, 0.4, "事项协作"),
]


def infer_emotion_coordinates(content: str, existing_label: str = "", existing_val: float = 0.0, existing_aro: float = 0.0):
    """Infer valence, arousal, and emotion_label from memory content if missing."""
    if existing_label and existing_label.strip() and (existing_val != 0.0 or existing_aro != 0.0):
        return existing_val, existing_aro, existing_label.strip()

    text = content.lower()
    for keywords, val, aro, label in EMOTION_HEURISTICS:
        if any(kw in text for kw in keywords):
            return val, aro, label

    return 0.0, 0.1, "日常事实"


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
        """Extract key noun entities from text using robust n-gram tokenization."""
        try:
            from anchor.recall.multi_retriever import MultiWayRetriever
            retriever = MultiWayRetriever(db_path=self.anchor_db_path)
            return retriever.extract_entities(content)
        except Exception:
            return []

    def run_backfill(self, max_items: Optional[int] = None) -> Dict[str, Any]:
        """Perform non-destructive migration into anchor_memories with offset-safe pagination."""
        legacy_file = Path(self.legacy_db_path)
        if not legacy_file.exists():
            logger.debug(f"Legacy database '{self.legacy_db_path}' does not exist. Skipping backfill.")
            return {"success": True, "migrated_count": 0, "skipped_count": 0, "status": "legacy_db_not_found"}

        try:
            with sqlite3.connect(self.legacy_db_path, timeout=5.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Get already migrated IDs from anchor_memories to prevent looping on the same limit batch
                with self.lt_service._db() as aconn:
                    acursor = aconn.cursor()
                    acursor.execute("SELECT id FROM anchor_memories WHERE id LIKE 'mem_legacy_%'")
                    migrated_ids = set(r["id"].replace("mem_legacy_", "") for r in acursor.fetchall())

                query = "SELECT * FROM memories WHERE deleted = 0 ORDER BY id ASC"
                cursor.execute(query)
                legacy_rows = cursor.fetchall()
        except Exception as e:
            logger.warning(f"Backfill read error: {e}")
            return {"success": False, "error": str(e)}

        migrated_count = 0
        skipped_count = 0
        limit = max_items or len(legacy_rows)

        for r in legacy_rows:
            leg_id_str = str(r["id"])
            if leg_id_str in migrated_ids:
                skipped_count += 1
                continue

            if migrated_count >= limit:
                break

            anchor_id = f"mem_legacy_{leg_id_str}"
            val, aro, label = infer_emotion_coordinates(
                r["content"],
                r["emotion_label"] or "",
                float(r["valence"] or 0.0),
                float(r["arousal"] or 0.0)
            )

            raw_imp = float(r["importance"] or 1)
            importance = min(1.0, max(0.1, raw_imp / 5.0)) if raw_imp > 1.0 else 0.5
            is_pinned = r["pinned"] if "pinned" in r.keys() else 0
            is_protected = 1 if is_pinned == 1 else 0

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
                is_protected=is_protected,
                source_date=str(r["created_at"])[:10],
                created_at=str(r["created_at"]),
                backfilled=1
            )
            migrated_count += 1

        logger.info(f"Backfill batch complete: {migrated_count} migrated, {skipped_count} skipped.")
        return {
            "success": True,
            "migrated_count": migrated_count,
            "skipped_count": skipped_count,
            "remaining": max(0, len(legacy_rows) - (skipped_count + migrated_count))
        }

    def backfill_batch(self, limit: int = 10) -> dict:
        """Batch backfill alias for Midnight pipeline."""
        return self.run_backfill(max_items=limit)


AnchorBackfillService = LegacyMemoryBackfillService
