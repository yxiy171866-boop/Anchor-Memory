"""Procedural Guide Service for Anchor Memory System.

Manages situation-aware behavior playbooks (Procedural Memory)
with 3-tier trigger matching, prompt pre-injection, and automatic deduplication.
"""
import re
import uuid
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Set

try:
    from anchor.db.connection import get_db
    from anchor.models.procedural_guide import ProceduralGuide
except ImportError:
    from db.connection import get_db
    from models.procedural_guide import ProceduralGuide

logger = logging.getLogger("anchor.procedural")

STOPWORDS = [
    "when", "if", "the", "an", "is", "are", "in", "on", "at", "to", "for", "with", "about",
    "user", "assistant", "companion", "partner", "friend", "someone",
    "伴侣", "朋友", "对方", "用户",
    "的时候", "在的", "发生", "出现", "比如", "以及", "一些", "场景", "场合", "任何",
    "在", "时", "如果", "和", "或", "与", "中", "跟", "有", "时候", "做", "被", "来", "去", "说", "看", "当"
]


def _extract_situation_keywords(situation: str) -> List[str]:
    """Extract conceptual keywords and n-grams from situation string, stripping noise."""
    clean = situation.lower()
    clean = re.sub(r'([\u4e00-\u9fff])([a-zA-Z0-9])', r'\1 \2', clean)
    clean = re.sub(r'([a-zA-Z0-9])([\u4e00-\u9fff])', r'\1 \2', clean)
    for noise in STOPWORDS:
        clean = clean.replace(noise, " ")
    clean = re.sub(r'[^\w\u4e00-\u9fff]+', ' ', clean)

    concepts = set()
    words = clean.split()
    for w in words:
        if re.match(r'^[a-z0-9_]+$', w):
            if len(w) >= 2:
                concepts.add(w)
        else:
            cjk_chars = [c for c in w if '\u4e00' <= c <= '\u9fff']
            cjk_str = ''.join(cjk_chars)
            if len(cjk_str) >= 2:
                concepts.add(cjk_str)
            for n in (2, 3):
                for i in range(len(cjk_str) - n + 1):
                    sub = cjk_str[i:i + n]
                    if len(sub) >= 2:
                        concepts.add(sub)
    return [t for t in concepts if len(t) >= 2]


def _combine_guidelines(old_text: str, new_text: str) -> str:
    """Intelligently combine existing guidelines with new ones without redundant duplicates."""
    old_clean = (old_text or "").strip()
    new_clean = (new_text or "").strip()
    if not old_clean:
        return new_clean
    if not new_clean:
        return old_clean
    if new_clean in old_clean:
        return old_clean
    if old_clean in new_clean:
        return new_clean
    return f"{old_clean}\n\n[Updated Addendum]:\n{new_clean}"


class ProceduralGuideService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def _db(self):
        if self.db_path:
            return get_db(self.db_path)
        return get_db()

    def find_similar_guide(self, situation: str) -> Optional[ProceduralGuide]:
        """Find an existing guide covering an identical or highly overlapping situation."""
        s_clean = re.sub(r'[^\w\u4e00-\u9fff]', '', situation.lower())
        if not s_clean:
            return None

        guides = self.get_all_guides()
        con_new = set(_extract_situation_keywords(situation))

        for guide in guides:
            g_clean = re.sub(r'[^\w\u4e00-\u9fff]', '', guide.situation.lower())
            # Exact clean match
            if s_clean == g_clean:
                return guide
            # Substring containment if long enough
            if min(len(s_clean), len(g_clean)) >= 6 and (s_clean in g_clean or g_clean in s_clean):
                return guide

            con_old = set(_extract_situation_keywords(guide.situation))
            if not con_new or not con_old:
                continue

            inter = con_new & con_old
            if not inter:
                continue

            containment = len(inter) / min(len(con_new), len(con_old))
            jaccard = len(inter) / len(con_new | con_old)

            if len(inter) >= 2:
                return guide
            if containment >= 0.35 or jaccard >= 0.25:
                return guide

        return None

    def create_guide(
        self,
        situation: str,
        playbook: str,
        taboos: str,
        confidence: float = 0.8,
        deduplicate: bool = True
    ) -> ProceduralGuide:
        """Create a new procedural guide item, or merge with an existing similar guide."""
        situation_clean = situation.strip()
        playbook_clean = playbook.strip()
        taboos_clean = taboos.strip()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if deduplicate:
            similar = self.find_similar_guide(situation_clean)
            if similar:
                logger.info(
                    f"Deduplicating procedural guide: '{situation_clean[:30]}' matches existing "
                    f"[{similar.id}] ('{similar.situation[:30]}'). Merging updates."
                )
                merged_playbook = _combine_guidelines(similar.playbook, playbook_clean)
                merged_taboos = _combine_guidelines(similar.taboos, taboos_clean)
                merged_situation = situation_clean if len(situation_clean) >= len(similar.situation) else similar.situation
                merged_conf = max(confidence, similar.confidence)

                with self._db() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        UPDATE anchor_procedural_guides
                        SET situation = ?, playbook = ?, taboos = ?, confidence = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (merged_situation, merged_playbook, merged_taboos, merged_conf, now, similar.id)
                    )

                res = ProceduralGuide(
                    id=similar.id,
                    situation=merged_situation,
                    playbook=merged_playbook,
                    taboos=merged_taboos,
                    confidence=merged_conf,
                    created_at=similar.created_at,
                    updated_at=now
                )
                res._is_updated = True
                return res

        guide_id = f"guide_{uuid.uuid4().hex[:8]}"
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO anchor_procedural_guides
                (id, situation, playbook, taboos, confidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (guide_id, situation_clean, playbook_clean, taboos_clean, confidence, now, now)
            )

        logger.info(f"Created procedural guide {guide_id}: {situation_clean[:30]}...")
        res = ProceduralGuide(
            id=guide_id,
            situation=situation_clean,
            playbook=playbook_clean,
            taboos=taboos_clean,
            confidence=confidence,
            created_at=now,
            updated_at=now
        )
        res._is_updated = False
        return res

    def update_guide(
        self,
        guide_id: str,
        situation: Optional[str] = None,
        playbook: Optional[str] = None,
        taboos: Optional[str] = None
    ) -> Optional[ProceduralGuide]:
        """Update an existing guide's situation, playbook or taboos."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updates = []
        params = []

        if situation:
            updates.append("situation = ?")
            params.append(situation.strip())
        if playbook:
            updates.append("playbook = ?")
            params.append(playbook.strip())
        if taboos:
            updates.append("taboos = ?")
            params.append(taboos.strip())

        if not updates:
            return None

        updates.append("updated_at = ?")
        params.append(now)
        params.append(guide_id)

        sql = f"UPDATE anchor_procedural_guides SET {', '.join(updates)} WHERE id = ?"
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            if cursor.rowcount > 0:
                cursor.execute("SELECT * FROM anchor_procedural_guides WHERE id = ?", (guide_id,))
                row = cursor.fetchone()
                if row:
                    return ProceduralGuide(**dict(row))
        return None

    def delete_guide(self, guide_id: str) -> bool:
        """Delete a procedural guide by ID."""
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM anchor_procedural_guides WHERE id = ?", (guide_id,))
            return cursor.rowcount > 0

    def get_all_guides(self) -> List[ProceduralGuide]:
        """Fetch all stored procedural guides."""
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM anchor_procedural_guides ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [ProceduralGuide(**dict(r)) for r in rows]

    def match_playbook(self, user_input: str) -> Optional[ProceduralGuide]:
        """Three-tier trigger matching against user input.

        Tier 1: Situation keywords presence in input
        Tier 2: Confidence threshold (>= 0.7)
        Tier 3: Best match selection by keyword overlap score
        """
        if not user_input or not user_input.strip():
            return None

        clean_input = user_input.lower().strip()
        guides = self.get_all_guides()
        if not guides:
            return None

        best_guide = None
        highest_score = 0.0

        for guide in guides:
            if guide.confidence < 0.7:
                continue

            keywords = _extract_situation_keywords(guide.situation)
            if not keywords:
                continue

            match_count = sum(1 for kw in keywords if kw in clean_input)
            if match_count == 0:
                continue

            score = match_count / max(1, len(keywords)) * guide.confidence
            if score > highest_score:
                highest_score = score
                best_guide = guide

        return best_guide if highest_score >= 0.3 else None

    def format_for_context(self, guide: Optional[ProceduralGuide]) -> str:
        """Format matched guide into a high-priority prompt directive."""
        if not guide:
            return ""

        return (
            "[CRITICAL BEHAVIOR PLAYBOOK · 专属行为与避坑指南]\n"
            f"⚠️ 触发情境: {guide.situation}\n"
            f"- 建议策略: {guide.playbook}\n"
            f"- 避雷禁忌: {guide.taboos}"
        )
