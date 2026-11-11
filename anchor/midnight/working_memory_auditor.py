"""Anchor Midnight Step 3 - Working Memory Prefrontal Audit.

Reviews active working memory items, purges expired items past buffer,
and identifies items that should be promoted to long-term memory.
"""
import logging
from typing import List, Dict, Any, Optional

try:
    from anchor.working_memory.service import WorkingMemoryService
    from anchor.config import ANCHOR_DB_PATH
except ImportError:
    from working_memory.service import WorkingMemoryService
    from config import ANCHOR_DB_PATH

logger = logging.getLogger("anchor.midnight.wm_auditor")


class WorkingMemoryAuditor:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or ANCHOR_DB_PATH
        self.wm_service = WorkingMemoryService(db_path=self.db_path)

    def audit_and_purge(
        self,
        resolved_items: Optional[List[Dict[str, str]]] = None,
        new_items: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Perform nightly audit: expire resolved items, add new commitments, purge buffer.

        Args:
            resolved_items: list of {'id': str, 'reason': str} to expire
            new_items: list of {'content': str, 'category': str} to add
        """
        expired_count = 0
        added_count = 0

        # Expire resolved items
        for item in (resolved_items or []):
            item_id = item.get("id", "")
            reason = item.get("reason", "resolved at midnight consolidation")
            if item_id:
                ok = self.wm_service.expire_item(item_id=item_id, reason=reason)
                if ok:
                    expired_count += 1

        # Add new commitments identified during consolidation
        for item in (new_items or []):
            content = item.get("content", "").strip()
            category = item.get("category", "general")
            if content:
                self.wm_service.add_item(content=content, category=category)
                added_count += 1

        # Purge items past buffer period
        purged = self.wm_service.purge_expired_buffer()

        active = self.wm_service.get_active_items()

        logger.info(f"WM Audit: expired={expired_count}, added={added_count}, purged={purged}, active={len(active)}")
        return {
            "expired_count": expired_count,
            "added_count": added_count,
            "purged_count": purged,
            "active_count": len(active),
        }
