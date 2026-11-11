"""Anchor Memory Search Tool with 3-Mode Support.

Modes:
- 'always': Mandatory search every turn
- 'never': Search tool disabled from toolset
- 'on_demand': Default recommended mode (AI searches when information is insufficient)
"""
import logging
from typing import Dict, Any, Optional

try:
    from anchor.config import ANCHOR_SEARCH_TOOL_MODE
    from anchor.recall.coordinator import AnchorRecallCoordinator
except ImportError:
    from config import ANCHOR_SEARCH_TOOL_MODE
    from recall.coordinator import AnchorRecallCoordinator

logger = logging.getLogger("anchor.search_tool")


class AnchorSearchTool:
    def __init__(self, db_path: Optional[str] = None, mode: Optional[str] = None):
        self.db_path = db_path
        self.mode = mode or ANCHOR_SEARCH_TOOL_MODE
        self.coordinator = AnchorRecallCoordinator(db_path=db_path)

    def is_tool_enabled(self) -> bool:
        """Check if the search tool should be exposed to the AI model."""
        return self.mode != "never"

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Execute memory search and return structured results."""
        return self.execute_search(query=query, limit=limit)

    def execute_search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Execute explicit memory search called by AI."""
        if not self.is_tool_enabled():
            return {
                "success": False,
                "error": "Memory search tool is disabled by system configuration (never mode).",
                "results": []
            }

        safe_limit = max(1, min(20, int(limit or 5)))
        results = self.coordinator.recall(query=query, top_k=safe_limit)

        clean_results = []
        for r in results:
            clean_results.append({
                "id": r["id"],
                "content": r["content"],
                "category": r.get("category", "general"),
                "emotion_label": r.get("emotion_label", "neutral"),
                "created_at": r.get("created_at", "")[:10],
                "score": r.get("recall_score", 0.0)
            })

        logger.info(f"anchor_memory_search '{query}' -> {len(clean_results)} hits.")
        return {
            "success": True,
            "query": query,
            "mode": self.mode,
            "count": len(clean_results),
            "results": clean_results
        }
