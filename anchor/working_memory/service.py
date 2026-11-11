"""Working Memory Service for Anchor.

Manages short-term ongoing background states (prefrontal cortex),
state transitions (active -> expired -> 2-day buffer auto-purge),
and bidirectional rescue.
"""
import uuid
import logging
from datetime import datetime
from typing import List, Optional

try:
    from anchor.db.connection import get_db
    from anchor.models.working_memory import WorkingMemoryItem
    from anchor.config import WORKING_MEMORY_BUFFER_DAYS
except ImportError:
    from db.connection import get_db
    from models.working_memory import WorkingMemoryItem
    from config import WORKING_MEMORY_BUFFER_DAYS

logger = logging.getLogger("anchor.working_memory")


class WorkingMemoryService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def _db(self):
        if self.db_path:
            return get_db(self.db_path)
        return get_db()

    def add_item(
        self,
        content: str,
        category: str = "general",
        created_by: str = "companion"
    ) -> WorkingMemoryItem:
        """Add a new item to working memory with status='active'."""
        item_id = f"wm_{uuid.uuid4().hex[:10]}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO anchor_working_memory
                (id, content, category, status, created_at, created_by, auto_clear_after_days)
                VALUES (?, ?, ?, 'active', ?, ?, ?)
                """,
                (item_id, content.strip(), category, now, created_by, WORKING_MEMORY_BUFFER_DAYS)
            )

        logger.info(f"Added working memory item {item_id}: {content[:30]}...")
        return WorkingMemoryItem(
            id=item_id,
            content=content.strip(),
            category=category,
            status="active",
            created_at=now,
            created_by=created_by,
            auto_clear_after_days=WORKING_MEMORY_BUFFER_DAYS
        )

    def update_item(self, item_id: str, content: str) -> bool:
        """Update ongoing details or progress for an existing item."""
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE anchor_working_memory
                SET content = ?
                WHERE id = ?
                """,
                (content.strip(), item_id)
            )
            updated = cursor.rowcount > 0

        if updated:
            logger.info(f"Updated working memory item {item_id}: {content[:30]}...")
        return updated

    def expire_item(self, item_id: str, reason: Optional[str] = None) -> bool:
        """Mark an item as expired (starts 2-day buffer period, strictly no hard delete).

        Supports exact ID match as well as keyword fallback match for usability.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        target_id = item_id.strip()

        with self._db() as conn:
            cursor = conn.cursor()
            # 1. Exact ID match
            cursor.execute(
                """
                UPDATE anchor_working_memory
                SET status = 'expired',
                    expired_at = ?,
                    expire_reason = ?
                WHERE id = ? AND status = 'active'
                """,
                (now, reason, target_id)
            )
            expired = cursor.rowcount > 0

            # 2. Fuzzy/keyword fallback (tolerates partial IDs like 'wm_task' or 'task')
            if not expired:
                cursor.execute(
                    """
                    SELECT id FROM anchor_working_memory
                    WHERE status = 'active'
                    ORDER BY created_at DESC
                    """
                )
                active_rows = cursor.fetchall()
                clean_target = target_id.lower().replace("wm_", "").strip()
                matched_id = None

                for r in active_rows:
                    aid = r["id"]
                    if clean_target and clean_target in aid.lower():
                        matched_id = aid
                        break

                if not matched_id and clean_target:
                    cursor.execute(
                        """
                        SELECT id FROM anchor_working_memory
                        WHERE status = 'active' AND content LIKE ?
                        LIMIT 1
                        """,
                        (f"%{clean_target}%",)
                    )
                    row = cursor.fetchone()
                    if row:
                        matched_id = row["id"]

                if matched_id:
                    cursor.execute(
                        """
                        UPDATE anchor_working_memory
                        SET status = 'expired', expired_at = ?, expire_reason = ?
                        WHERE id = ? AND status = 'active'
                        """,
                        (now, reason, matched_id)
                    )
                    expired = cursor.rowcount > 0

        if expired:
            logger.info(f"Expired working memory item {item_id} (reason: {reason})")
        return expired

    def restore_item(self, item_id: str, restore_reason: str = "false positive recovery") -> Optional[WorkingMemoryItem]:
        """Rescue: restore an expired-buffer item back to active state."""
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE anchor_working_memory
                SET status = 'active', expired_at = NULL, expire_reason = ?
                WHERE id = ? AND status = 'expired'
                """,
                (f"[RESTORED] {restore_reason}", item_id)
            )
            restored = cursor.rowcount > 0

            if restored:
                cursor.execute(
                    "SELECT * FROM anchor_working_memory WHERE id = ?", (item_id,)
                )
                row = cursor.fetchone()
                if row:
                    return WorkingMemoryItem(**dict(row))
        return None

    def get_active_items(self) -> List[WorkingMemoryItem]:
        """Get all currently active working memory items."""
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM anchor_working_memory
                WHERE status = 'active'
                ORDER BY created_at DESC
                """
            )
            rows = cursor.fetchall()
            return [WorkingMemoryItem(**dict(r)) for r in rows]

    def purge_expired_buffer(self) -> int:
        """Hard-delete expired items that have exceeded the buffer period. Called by midnight pipeline."""
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=WORKING_MEMORY_BUFFER_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM anchor_working_memory
                WHERE status = 'expired' AND expired_at < ?
                """,
                (cutoff,)
            )
            count = cursor.rowcount
        logger.info(f"Purged {count} expired working memory items past buffer period.")
        return count

    def format_for_context(self) -> str:
        """Format active items as a concise markdown block for prompt pre-injection."""
        items = self.get_active_items()
        if not items:
            return ""

        lines = ["[Current Working Memory · 前额叶实时背景 (进行中状态)]"]
        for it in items:
            date_str = it.created_at[:10] if it.created_at else ""
            lines.append(f"- [ID: {it.id} | {it.category}] {it.content} ({date_str})")
        return "\n".join(lines)
