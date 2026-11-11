"""Long-term Memory Service for Anchor.

Manages episodic & semantic memories, emotional coordinate tagging,
provenance tracking, hard protection (is_protected), version superseding,
and single-transaction periodic Ebbinghaus decay updates.
"""
import json
import uuid
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

try:
    from anchor.db.connection import get_db
    from anchor.models.memory_item import MemoryItem
    from anchor.long_term.decay import calculate_decay_score
except ImportError:
    from db.connection import get_db
    from models.memory_item import MemoryItem
    from long_term.decay import calculate_decay_score

logger = logging.getLogger("anchor.long_term")


class LongTermMemoryService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def _db(self):
        if self.db_path:
            return get_db(self.db_path)
        return get_db()

    def create_memory(
        self,
        content: str,
        category: str = "general",
        importance: Optional[float] = None,
        valence: float = 0.0,
        arousal: float = 0.0,
        emotion_label: str = "neutral",
        entities: Optional[List[str]] = None,
        links: Optional[List[str]] = None,
        custom_id: Optional[str] = None,
        is_protected: int = 0,
        source_message_id: Optional[str] = None,
        source_date: Optional[str] = None,
        confidence: float = 1.0,
        created_at: Optional[str] = None,
        backfilled: int = 0
    ) -> MemoryItem:
        """Create a new long-term memory entry with provenance and protection."""
        memory_id = custom_id or f"mem_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
        now = created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Safe importance parsing: allows 0.0, clamps to [0.0, 1.0]
        safe_importance = 0.5 if importance is None else max(0.0, min(1.0, float(importance)))
        safe_valence = max(-1.0, min(1.0, float(valence if valence is not None else 0.0)))
        safe_arousal = max(0.0, min(1.0, float(arousal if arousal is not None else 0.0)))

        # Guarantee entities and links are serializable lists
        safe_entities = list(entities) if entities is not None else []
        safe_links = list(links) if links is not None else []
        entities_json = json.dumps(safe_entities, ensure_ascii=False)
        links_json = json.dumps(safe_links, ensure_ascii=False)

        # Initial decay score equals initial importance
        decay_score = calculate_decay_score(
            safe_importance, safe_arousal, days_elapsed=0.0, is_protected=bool(is_protected)
        )

        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO anchor_memories
                (id, content, category, importance, valence, arousal, emotion_label,
                 entities, links, decay_score, status, is_protected, source_message_id,
                 source_date, confidence, backfilled, created_at, updated_at, last_accessed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (memory_id, content.strip(), category, safe_importance, safe_valence, safe_arousal,
                 emotion_label, entities_json, links_json, decay_score, is_protected,
                 source_message_id, source_date, confidence, backfilled, now, now, now)
            )

        logger.info(f"Created long-term memory {memory_id}: {content[:40]}... (protected={is_protected})")
        return MemoryItem(
            id=memory_id,
            content=content.strip(),
            category=category,
            importance=safe_importance,
            valence=safe_valence,
            arousal=safe_arousal,
            emotion_label=emotion_label,
            entities=safe_entities,
            links=safe_links,
            decay_score=decay_score,
            status="active",
            is_protected=is_protected,
            source_message_id=source_message_id,
            source_date=source_date,
            confidence=confidence,
            backfilled=backfilled,
            created_at=now,
            updated_at=now,
            last_accessed_at=now
        )

    def get_memory(self, memory_id: str) -> Optional[MemoryItem]:
        """Retrieve a memory by ID."""
        clean_id = str(memory_id).strip()
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM anchor_memories WHERE id = ?",
                (clean_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            for field in ("entities", "links"):
                try:
                    d[field] = json.loads(d.get(field) or "[]")
                except Exception:
                    d[field] = []
            return MemoryItem(**d)

    def update_memory(
        self,
        memory_id: str,
        mode: str = "replace",
        content: str = "",
        importance: Optional[float] = None,
        is_protected: Optional[int] = None
    ) -> bool:
        """Update memory content or protection status."""
        mem = self.get_memory(memory_id)
        if not mem:
            logger.warning(f"Memory {memory_id} not found for update")
            return False

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_content = content.strip() if mode == "replace" else f"{mem.content}\n{content.strip()}"

        updates = ["content = ?", "updated_at = ?"]
        params = [new_content, now]

        if importance is not None:
            updates.append("importance = ?")
            params.append(max(0.0, min(1.0, float(importance))))

        if is_protected is not None:
            updates.append("is_protected = ?")
            params.append(int(is_protected))

        params.append(mem.id)
        sql = f"UPDATE anchor_memories SET {', '.join(updates)} WHERE id = ?"

        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            updated = cursor.rowcount > 0

        if updated:
            logger.info(f"Updated memory {mem.id} ({mode})")
        return updated

    def supersede_memory(self, old_memory_id: str, new_content: str, reason: str) -> Optional[MemoryItem]:
        """Create a new memory that supersedes an old one; old is marked as 'superseded'.

        Guards against overwriting protected memories without user permission.
        """
        old_mem = self.get_memory(old_memory_id)
        if not old_mem:
            logger.warning(f"Memory {old_memory_id} not found for supersede")
            return None

        if old_mem.is_protected:
            logger.warning(f"Memory {old_memory_id} is marked as is_protected=1. Automatic supersede is rejected.")
            return None

        # Create new memory inheriting coordinates and linking to previous version
        new_mem = self.create_memory(
            content=new_content,
            category=old_mem.category,
            importance=old_mem.importance,
            valence=old_mem.valence,
            arousal=old_mem.arousal,
            emotion_label=old_mem.emotion_label,
            entities=old_mem.entities,
            links=[old_mem.id] + old_mem.links,
            source_date=datetime.now().strftime("%Y-%m-%d"),
            confidence=1.0
        )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE anchor_memories
                SET status = 'superseded', superseded_by = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_mem.id, now, old_mem.id)
            )

        logger.info(f"Memory {old_mem.id} superseded by {new_mem.id} (reason: {reason})")
        return new_mem

    def add_note(self, memory_id: str, author: str, content: str) -> Optional[Dict[str, Any]]:
        """Append a note/annotation to an existing memory without altering original text."""
        mem = self.get_memory(memory_id)
        if not mem:
            logger.warning(f"Cannot add note to non-existent memory {memory_id}")
            return None

        real_mem_id = mem.id
        note_id = f"note_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO anchor_memory_notes (id, memory_id, author, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (note_id, real_mem_id, author, content.strip(), now)
            )
            # Reinforce memory retention by updating last_accessed_at
            cursor.execute(
                "UPDATE anchor_memories SET last_accessed_at = ? WHERE id = ?",
                (now, real_mem_id)
            )

        logger.info(f"Added note {note_id} by {author} to memory {real_mem_id}")
        return {
            "id": note_id,
            "memory_id": real_mem_id,
            "author": author,
            "content": content.strip(),
            "created_at": now
        }

    def get_notes(self, memory_id: str) -> List[Dict[str, Any]]:
        """Fetch all notes for a specific memory item in chronological order."""
        mem = self.get_memory(memory_id)
        real_mem_id = mem.id if mem else str(memory_id).strip()
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM anchor_memory_notes WHERE memory_id = ? ORDER BY created_at ASC",
                (real_mem_id,)
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_all_active(self) -> List[MemoryItem]:
        """Fetch all active memories for recall processing."""
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM anchor_memories
                WHERE status = 'active'
                ORDER BY decay_score DESC, importance DESC
                """
            )
            rows = cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                for field in ("entities", "links"):
                    try:
                        d[field] = json.loads(d.get(field) or "[]")
                    except Exception:
                        d[field] = []
                result.append(MemoryItem(**d))
            return result

    def recalculate_all_decay_scores(self) -> int:
        """Recompute Ebbinghaus decay scores for all active memories in a single atomic transaction."""
        now = datetime.now()
        active = self.get_all_active()
        if not active:
            return 0

        updates = []
        for mem in active:
            try:
                created = datetime.strptime(mem.created_at[:19], "%Y-%m-%d %H:%M:%S")
                days_elapsed = (now - created).total_seconds() / 86400.0
            except Exception:
                days_elapsed = 0.0

            new_score = calculate_decay_score(
                mem.importance, mem.arousal, days_elapsed, is_protected=bool(mem.is_protected)
            )
            updates.append((new_score, mem.id))

        with self._db() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "UPDATE anchor_memories SET decay_score = ? WHERE id = ?",
                updates
            )

        logger.info(f"Recalculated decay scores for {len(updates)} active memories in 1 transaction.")
        return len(updates)
