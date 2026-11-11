"""Anchor Midnight Step 1 - Daily Dialogue Compression.

Compresses the day's conversation into a 500-800 word narrative
written in the companion's voice, covering:
1. What happened today (overall atmosphere)
2. Emotional states and key shifts
3. Important events, decisions, and commitments
4. Unresolved topics or pending tasks
5. Relationship dynamics worth noting
"""
import logging
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    from anchor.config import (
        ANCHOR_DB_PATH,
        CHAT_DB_PATH,
        MIDNIGHT_SUMMARY_MIN_WORDS,
        MIDNIGHT_SUMMARY_MAX_WORDS,
        COMPANION_NAME,
        USER_NAME,
    )
    from anchor.db.connection import get_db
except ImportError:
    from config import (
        ANCHOR_DB_PATH,
        CHAT_DB_PATH,
        MIDNIGHT_SUMMARY_MIN_WORDS,
        MIDNIGHT_SUMMARY_MAX_WORDS,
        COMPANION_NAME,
        USER_NAME,
    )
    from db.connection import get_db

logger = logging.getLogger("anchor.midnight.compressor")


class DialogueCompressor:
    def __init__(self, db_path: Optional[str] = None, chat_db_path: Optional[str] = None):
        self.db_path = db_path or ANCHOR_DB_PATH
        self.chat_db_path = chat_db_path or CHAT_DB_PATH

    def _db(self):
        return get_db(self.db_path)

    def fetch_day_messages(self, target_date: str) -> List[Dict[str, Any]]:
        """Fetch all chat messages for target_date (YYYY-MM-DD) from configured chat DB.
        
        Expects a table named 'chat_messages' with columns: id, role, content, created_at.
        Configure ANCHOR_CHAT_DB_PATH to point to your application's chat database.
        """
        if not self.chat_db_path:
            logger.warning("No chat DB path configured. Set ANCHOR_CHAT_DB_PATH.")
            return []

        try:
            with sqlite3.connect(str(self.chat_db_path), timeout=5.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, role, content, created_at
                    FROM chat_messages
                    WHERE created_at LIKE ?
                    ORDER BY id ASC
                    """,
                    (f"{target_date}%",)
                )
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to fetch messages for date {target_date}: {e}")
            return []

    def compress_dialogue(
        self,
        messages: List[Dict[str, Any]],
        target_date: str,
        custom_narrative: Optional[str] = None
    ) -> str:
        """Produce a {MIDNIGHT_SUMMARY_MIN_WORDS}-{MIDNIGHT_SUMMARY_MAX_WORDS} word narrative summary.

        If custom_narrative is provided (from an external AI call), it is used directly.
        Otherwise, generates a simple structural digest from messages.
        """
        if custom_narrative and len(custom_narrative.strip()) > 50:
            return custom_narrative.strip()

        if not messages:
            return f"[{target_date}] No conversation recorded for this day."

        # Build a minimal structural digest when no AI narrative is provided
        user_msgs = [m for m in messages if m.get("role") == "user"]
        assistant_msgs = [m for m in messages if m.get("role") in ("assistant", "companion")]

        lines = [
            f"[Daily Digest: {target_date}]",
            f"Total messages: {len(messages)} ({len(user_msgs)} from {USER_NAME}, {len(assistant_msgs)} from {COMPANION_NAME})",
            "",
            "--- Conversation Highlights ---",
        ]

        # Include up to 10 user messages as highlights
        for msg in user_msgs[:10]:
            content = (msg.get("content") or "")[:200]
            lines.append(f"[{USER_NAME}]: {content}")

        return "\n".join(lines)
