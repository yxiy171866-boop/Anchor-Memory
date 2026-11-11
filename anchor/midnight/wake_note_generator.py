"""Anchor Midnight Step 4 - Morning Wake Note Generator.

Generates a brief, warm morning note summarizing what happened
and what to pay attention to for the upcoming day.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

try:
    from anchor.config import COMPANION_NAME, USER_NAME
    from anchor.working_memory.service import WorkingMemoryService
except ImportError:
    from config import COMPANION_NAME, USER_NAME
    from working_memory.service import WorkingMemoryService

logger = logging.getLogger("anchor.midnight.wake_note")


class WakeNoteGenerator:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.wm_service = WorkingMemoryService(db_path=db_path)

    def generate_wake_note(
        self,
        daily_digest: str,
        target_date: str,
        custom_wake_note: Optional[str] = None
    ) -> str:
        """Generate a morning wake note for the next session.

        If custom_wake_note is provided (from an external AI call), it is used directly.
        Otherwise, generates a simple structural note.
        """
        if custom_wake_note and len(custom_wake_note.strip()) > 20:
            return custom_wake_note.strip()

        # Get active working memory items
        active_items = self.wm_service.get_active_items()
        tomorrow = (datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

        lines = [
            f"[Morning Note for {tomorrow}]",
            "",
            "Things to keep in mind from yesterday:",
        ]

        for item in active_items[:5]:
            lines.append(f"- [{item.category}] {item.content}")

        if not active_items:
            lines.append("- Nothing pending from the working memory buffer.")

        return "\n".join(lines)
