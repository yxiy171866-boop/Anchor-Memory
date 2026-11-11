"""Conversation History Retrieval Tool for Anchor.

Provides semantic and keyword search across past chat messages
with flexible scoping (recent/7d/30d/90d/all) and optional date ranges.
"""
import json
import math
import re
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

try:
    from anchor.config import CHAT_DB_PATH
    from anchor.recall.embedder import AnchorEmbedder
except ImportError:
    from config import CHAT_DB_PATH
    from recall.embedder import AnchorEmbedder

logger = logging.getLogger("anchor.recall.chat_history")

LATIN_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*")
CHINESE_RUN_RE = re.compile(r"[\u3400-\u9fff]+")

CHINESE_STOP_FRAGMENTS = {
    "一个", "那个", "这个", "我们", "你们", "他们", "自己", "什么", "怎么",
    "就是", "还是", "已经", "现在", "之前", "之后", "时候", "可以", "可能",
    "因为", "所以", "但是", "然后", "一下", "一些", "有关", "关于",
}


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    text = str(text)
    tokens = [item.lower() for item in LATIN_TOKEN_RE.findall(text)]
    for run in CHINESE_RUN_RE.findall(text):
        length = len(run)
        for size in (2, 3, 4):
            if length < size:
                continue
            for index in range(length - size + 1):
                frag = run[index:index + size]
                if frag not in CHINESE_STOP_FRAGMENTS:
                    tokens.append(frag)
    return list(dict.fromkeys(tokens))


def _keyword_score(query_tokens: List[str], content: str) -> float:
    content_tokens = set(_tokenize(content))
    hits = sum(1 for token in query_tokens if token in content_tokens)
    return float(hits)


class ConversationSearchTool:
    def __init__(self, chat_db_path: Optional[str] = None):
        self.chat_db_path = chat_db_path or CHAT_DB_PATH
        self.embedder = AnchorEmbedder()

    def _scope_to_start_time(self, scope: str) -> Optional[str]:
        scope = (scope or "recent").strip().lower()
        now = datetime.now()
        if scope == "recent":
            return (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        if scope == "7d":
            return (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        if scope == "30d":
            return (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        if scope == "90d":
            return (now - timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")
        if scope == "all":
            return None
        return (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")

    def search_conversation(
        self,
        query: str,
        limit: int = 6,
        scope: str = "recent",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search chat messages by query, scope, or specific date range."""
        query = (query or "").strip()
        if not query:
            return {"error": "Query is required", "results": []}

        limit = max(1, min(int(limit or 6), 20))
        start_time = None
        end_time = None

        if start_date or end_date:
            if start_date:
                s = str(start_date).strip()
                start_time = f"{s} 00:00:00" if len(s) == 10 else s
            if end_date:
                e = str(end_date).strip()
                end_time = f"{e} 23:59:59" if len(e) == 10 else e
        else:
            start_time = self._scope_to_start_time(scope)

        query_tokens = _tokenize(query)
        query_vec = self.embedder.get_embedding(query)

        try:
            with sqlite3.connect(str(self.chat_db_path), timeout=5.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Flexible schema check: filter conversation_id if column exists
                where_clauses = []
                params = []

                if conversation_id:
                    where_clauses.append("conversation_id = ?")
                    params.append(conversation_id)

                if start_time:
                    where_clauses.append("created_at >= ?")
                    params.append(start_time)

                if end_time:
                    where_clauses.append("created_at <= ?")
                    params.append(end_time)

                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
                sql = f"SELECT id, role, content, created_at FROM chat_messages {where_sql} ORDER BY id DESC"
                
                cursor.execute(sql, params)
                rows = cursor.fetchall()
        except Exception as e:
            logger.warning(f"Failed to query chat_messages: {e}")
            return {"error": str(e), "results": []}

        ranked = []
        for r in rows:
            content = r["content"] or ""
            kw_score = _keyword_score(query_tokens, content)
            msg_vec = self.embedder.get_embedding(content)
            sem_score = self.embedder.cosine_similarity(query_vec, msg_vec)

            # Combined score
            kw_bonus = min(kw_score, 1.5)
            retrieval_score = sem_score * 10.0 + kw_bonus

            if sem_score < 0.30 and kw_score <= 0:
                continue

            ranked.append({
                "id": r["id"],
                "role": r["role"],
                "content": content,
                "created_at": r["created_at"],
                "semantic_score": round(sem_score, 3),
                "keyword_score": round(kw_score, 1),
                "score": round(retrieval_score, 3)
            })

        ranked.sort(key=lambda x: (x["score"], x["semantic_score"]), reverse=True)
        top_results = ranked[:limit]

        used_scope = f"{start_date}~{end_date}" if (start_date or end_date) else scope
        return {
            "query": query,
            "scope": used_scope,
            "count": len(top_results),
            "results": top_results
        }
