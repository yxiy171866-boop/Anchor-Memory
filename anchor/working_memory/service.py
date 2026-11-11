"""Working Memory Service for Anchor.

Manages short-term ongoing background states (prefrontal cortex),
state transitions (active -> expired -> 2-day buffer -> archived),
no physical hard deletes, strict ID validation with helpful candidates,
and auto-expiry checking based on elapsed time.
"""
import uuid
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

try:
    from anchor.db.connection import get_db
    from anchor.models.working_memory import WorkingMemoryItem
    from anchor.config import WORKING_MEMORY_BUFFER_DAYS
except ImportError:
    from db.connection import get_db
    from models.working_memory import WorkingMemoryItem
    from config import WORKING_MEMORY_BUFFER_DAYS

logger = logging.getLogger("anchor.working_memory")


def _format_buffer_countdown(expired_at_str: Optional[str], buffer_days: int = 2) -> str:
    """Format remaining countdown before an expired buffer item is archived."""
    if not expired_at_str:
        return "Expired · In Buffer"
    try:
        exp_dt = datetime.strptime(expired_at_str, "%Y-%m-%d %H:%M:%S")
        total_seconds = buffer_days * 86400
        passed_seconds = (datetime.now() - exp_dt).total_seconds()
        remaining_seconds = total_seconds - passed_seconds
        if remaining_seconds <= 0:
            return "Expired · Archiving Soon"
        remaining_hours = int(remaining_seconds // 3600)
        if remaining_hours >= 24:
            days = remaining_hours // 24
            hours = remaining_hours % 24
            return f"Expired · {days}d {hours}h until archive"
        return f"Expired · {remaining_hours}h until archive"
    except Exception:
        return "Expired · In Buffer"


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
        created_by: str = "companion",
        auto_clear_after_days: int = WORKING_MEMORY_BUFFER_DAYS
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
                (item_id, content.strip(), category, now, created_by, auto_clear_after_days)
            )

        logger.info(f"Added working memory item {item_id}: {content[:30]}...")
        return WorkingMemoryItem(
            id=item_id,
            content=content.strip(),
            category=category,
            status="active",
            created_at=now,
            created_by=created_by,
            auto_clear_after_days=auto_clear_after_days
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
                (content.strip(), item_id.strip())
            )
            updated = cursor.rowcount > 0

        if updated:
            logger.info(f"Updated working memory item {item_id}: {content[:30]}...")
        return updated

    def expire_item(self, item_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """Mark an item as expired (starts 2-day buffer period).

        STRICT: Only exact ID matching is allowed to prevent accidental deletion.
        If not found, returns success=False and a candidate list of active items.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        target_id = item_id.strip()

        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE anchor_working_memory
                SET status = 'expired',
                    expired_at = ?,
                    expire_reason = ?
                WHERE id = ? AND status = 'active'
                """,
                (now, reason or "resolved", target_id)
            )
            expired = cursor.rowcount > 0

        if expired:
            logger.info(f"Expired working memory item {target_id} (reason: {reason})")
            return {"success": True, "item_id": target_id, "message": f"Item [{target_id}] marked as expired."}

        # Provide candidate list to guide model or user
        active_items = self.get_active_items()
        candidates = [{"id": it.id, "content": it.content[:40]} for it in active_items]
        return {
            "success": False,
            "error": f"Item with ID '{target_id}' not found in active items.",
            "candidates": candidates
        }

    def restore_item(self, item_id: str, restore_reason: str = "false positive recovery") -> Optional[WorkingMemoryItem]:
        """Rescue an expired-buffer item back to 'active' status."""
        target_id = item_id.strip()
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE anchor_working_memory
                SET status = 'active', expired_at = NULL, expire_reason = ?
                WHERE id = ? AND status = 'expired'
                """,
                (f"[RESTORED] {restore_reason}", target_id)
            )
            restored = cursor.rowcount > 0

            if restored:
                cursor.execute(
                    "SELECT * FROM anchor_working_memory WHERE id = ?", (target_id,)
                )
                row = cursor.fetchone()
                if row:
                    return WorkingMemoryItem(**dict(row))
        return None

    def get_active_items(self) -> List[WorkingMemoryItem]:
        """Fetch all currently active working memory items (auto-refreshing elapsed timeouts)."""
        # First trigger check for items that exceeded auto_clear_after_days
        self.check_and_expire_overdue_items()

        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, content, category, status, created_at, created_by,
                       expired_at, expire_reason, auto_clear_after_days
                FROM anchor_working_memory
                WHERE status = 'active'
                ORDER BY created_at DESC
                """
            )
            rows = cursor.fetchall()
            return [WorkingMemoryItem(**dict(r)) for r in rows]

    def check_and_expire_overdue_items(self) -> int:
        """Automatically transition active items to 'expired' if they exceeded auto_clear_after_days."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE anchor_working_memory
                SET status = 'expired',
                    expired_at = ?,
                    expire_reason = 'auto-expired after duration timeout'
                WHERE status = 'active'
                  AND julianday('now') - julianday(created_at) >= auto_clear_after_days
                """,
                (now,)
            )
            count = cursor.rowcount

        if count > 0:
            logger.info(f"Auto-expired {count} overdue active working memory items.")
        return count

    def get_expired_buffer(self) -> List[WorkingMemoryItem]:
        """Fetch items currently in the 2-day recovery buffer."""
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, content, category, status, created_at, created_by,
                       expired_at, expire_reason, auto_clear_after_days
                FROM anchor_working_memory
                WHERE status = 'expired'
                ORDER BY expired_at DESC
                """
            )
            rows = cursor.fetchall()
            return [WorkingMemoryItem(**dict(r)) for r in rows]

    def purge_expired_buffer(self, buffer_days: int = WORKING_MEMORY_BUFFER_DAYS) -> int:
        """NO HARD DELETE: Transition expired buffer items older than buffer_days to 'archived' status."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE anchor_working_memory
                SET status = 'archived',
                    archived_at = ?
                WHERE status = 'expired'
                  AND (julianday('now') - julianday(expired_at) >= ? OR ? <= 0)
                """,
                (now, buffer_days, buffer_days)
            )
            count = cursor.rowcount

        if count > 0:
            logger.info(f"Safely archived {count} expired items past buffer (no physical hard delete).")
        return count

    def format_for_context(self) -> str:
        """Format active items and 2-day expired buffer items with countdowns for prompt pre-injection."""
        active_items = self.get_active_items()
        buffer_items = self.get_expired_buffer()

        if not active_items and not buffer_items:
            return ""

        lines = ["[Current Working Memory · Active Context & Buffer]"]

        # 1. Active items
        if active_items:
            lines.append("* Active Items (In Progress):")
            for it in active_items:
                date_str = it.created_at[:10] if it.created_at else ""
                lines.append(f"- [ID: {it.id} | {it.category}] {it.content} ({date_str})")
        else:
            lines.append("* Active Items: (none currently active)")

        # 2. Expired buffer items (recoverable via restore tool)
        if buffer_items:
            lines.append("\n* Expired Buffer (Call working_memory_restore within 2 days to recover, auto-archived afterwards):")
            for it in buffer_items:
                countdown_tag = _format_buffer_countdown(it.expired_at, getattr(it, "auto_clear_after_days", 2) or 2)
                reason_str = f" [Reason: {it.expire_reason}]" if getattr(it, "expire_reason", None) else ""
                lines.append(f"- [ID: {it.id} | {countdown_tag}{reason_str}] {it.content}")

        return "\n".join(lines)
