"""Multi-Way Memory Retriever for Anchor.

Provides four independent retrieval signals with robust Chinese & Latin n-gram extraction:
1. Semantic similarity (embedding cosine)
2. Entity/keyword overlap (Chinese n-gram + Latin word tokens)
3. Emotional coordinate proximity (valence + arousal distance)
4. Recency / interaction freshness (based on last_accessed_at)
"""
import json
import logging
import math
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Set

try:
    from anchor.recall.embedder import AnchorEmbedder
    from anchor.db.connection import get_db
    from anchor.config import RECALL_MIN_SCORE_THRESHOLD
except ImportError:
    from recall.embedder import AnchorEmbedder
    from db.connection import get_db
    from config import RECALL_MIN_SCORE_THRESHOLD

logger = logging.getLogger("anchor.recall.retriever")

LATIN_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*")
CHINESE_RUN_RE = re.compile(r"[\u3400-\u9fff]+")

CHINESE_STOP_FRAGMENTS = {
    "一个", "那个", "这个", "我们", "你们", "他们", "自己", "什么", "怎么",
    "就是", "还是", "已经", "现在", "之前", "之后", "时候", "可以", "可能",
    "因为", "所以", "但是", "然后", "一下", "一些", "有关", "关于", "喜欢"
}


def extract_robust_tokens(text: str) -> Set[str]:
    """Extract Latin words and Chinese 2/3/4-grams from text to guarantee Chinese entity matching."""
    if not text:
        return set()
    text = str(text)
    tokens = set(item.lower() for item in LATIN_TOKEN_RE.findall(text))

    for run in CHINESE_RUN_RE.findall(text):
        length = len(run)
        if length <= 4:
            if run not in CHINESE_STOP_FRAGMENTS and len(run) >= 2:
                tokens.add(run)
        for size in (2, 3, 4):
            if length < size:
                continue
            for index in range(length - size + 1):
                frag = run[index:index + size]
                if frag not in CHINESE_STOP_FRAGMENTS:
                    tokens.add(frag)
    return tokens


class MultiWayRetriever:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.embedder = AnchorEmbedder(db_path=db_path)

    def _db(self):
        if self.db_path:
            return get_db(self.db_path)
        return get_db()

    def fetch_active_memories(self) -> List[Dict[str, Any]]:
        """Fetch all active memories as plain dicts for retrieval processing."""
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, content, category, importance, valence, arousal,
                       emotion_label, entities, decay_score, is_protected,
                       created_at, last_accessed_at
                FROM anchor_memories
                WHERE status = 'active'
                ORDER BY decay_score DESC
                """
            )
            rows = cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                try:
                    d["entities"] = json.loads(d.get("entities") or "[]")
                except Exception:
                    d["entities"] = []
                result.append(d)
            return result

    def retrieve_by_semantic(self, query: str, memories: List[Dict[str, Any]]) -> Dict[str, float]:
        """Compute cosine similarity between query embedding and each memory's embedding."""
        if not query or not memories:
            return {}

        query_vec = self.embedder.get_embedding_vector(query)
        query_dim = len(query_vec)
        scores = {}
        for mem in memories:
            mem_vec = self.embedder.get_cached_embedding(mem["id"], mem["content"], expected_dim=query_dim)
            scores[mem["id"]] = self.embedder.cosine_similarity(query_vec, mem_vec)
        return scores

    def retrieve_by_entity(self, query: str, memories: List[Dict[str, Any]]) -> Dict[str, float]:
        """Score memories by robust Chinese & Latin keyword/entity overlap."""
        if not query or not memories:
            return {}

        query_tokens = extract_robust_tokens(query)
        if not query_tokens:
            return {}

        scores = {}
        for mem in memories:
            # Check explicit entities list + memory text tokens
            explicit_entities = set(str(e).lower() for e in (mem.get("entities") or []))
            content_tokens = extract_robust_tokens(mem["content"])

            all_mem_tokens = explicit_entities | content_tokens
            overlap = query_tokens & all_mem_tokens

            # Score by overlap proportion
            score = len(overlap) / max(1, len(query_tokens))
            scores[mem["id"]] = min(1.0, score)

        return scores

    def retrieve_by_emotion(
        self,
        query: str,
        memories: List[Dict[str, Any]],
        detected_valence: Optional[float] = None,
        detected_arousal: Optional[float] = None,
        detected_label: Optional[str] = None
    ) -> Dict[str, float]:
        """Score memories by proximity in emotional coordinate space."""
        if not memories:
            return {}

        q_val = float(detected_valence) if detected_valence is not None else 0.0
        q_aro = float(detected_arousal) if detected_arousal is not None else 0.0

        scores = {}
        for mem in memories:
            m_val = float(mem.get("valence") if mem.get("valence") is not None else 0.0)
            m_aro = float(mem.get("arousal") if mem.get("arousal") is not None else 0.0)

            # Euclidean distance in 2D emotion space
            dist = math.sqrt((q_val - m_val) ** 2 + (q_aro - m_aro) ** 2)
            score = max(0.0, 1.0 - dist / 2.83)

            # Boost if emotion label matches
            if detected_label and detected_label == mem.get("emotion_label"):
                score = min(1.0, score + 0.2)

            scores[mem["id"]] = score
        return scores

    def retrieve_by_recency(self, memories: List[Dict[str, Any]]) -> Dict[str, float]:
        """Score memories by recent interaction / access freshness (does NOT duplicate decay)."""
        if not memories:
            return {}

        now = datetime.now()
        scores = {}
        for mem in memories:
            ts_str = mem.get("last_accessed_at") or mem.get("created_at") or ""
            try:
                ts = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
                days_ago = (now - ts).total_seconds() / 86400.0
                # Recent access boost within 14 days
                score = math.exp(-days_ago / 14.0)
            except Exception:
                score = 0.0
            scores[mem["id"]] = score
        return scores

    def extract_entities(self, text: str) -> List[str]:
        """Extract entity list from text, returning a JSON-serializable list."""
        tokens = extract_robust_tokens(text)
        return list(tokens)
