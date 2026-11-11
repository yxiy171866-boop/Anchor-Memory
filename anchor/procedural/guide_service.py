"""Procedural Guide Service for Anchor Memory System.

Manages situation-aware behavior playbooks (Procedural Memory)
with 3-tier trigger matching and prompt pre-injection.
"""
import uuid
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

try:
    from anchor.db.connection import get_db
    from anchor.models.procedural_guide import ProceduralGuide
except ImportError:
    from db.connection import get_db
    from models.procedural_guide import ProceduralGuide

logger = logging.getLogger("anchor.procedural")


def _extract_situation_keywords(situation: str) -> List[str]:
    """Extract 2-3 char conceptual keywords from situation string, stripping noise words."""
    # Strip common noise patterns (customize for your language)
    noise_words = ["when", "if", "the", "a", "is", "are", "occurs", "happens"]
    words = situation.lower().split()
    tokens = set()
    for word in words:
        clean = word.strip(".,!?;:\"'")
        if clean and clean not in noise_words and len(clean) >= 2:
            tokens.add(clean)
            # Also add sub-sequences for CJK / compound matching
            for n in (2, 3):
                for i in range(len(clean) - n + 1):
                    tokens.add(clean[i:i + n])
    return [t for t in tokens if len(t) >= 2]


class ProceduralGuideService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def _db(self):
        if self.db_path:
            return get_db(self.db_path)
        return get_db()

    def create_guide(
        self,
        situation: str,
        playbook: str,
        taboos: str,
        confidence: float = 0.8
    ) -> ProceduralGuide:
        """Create a new procedural guide item."""
        guide_id = f"guide_{uuid.uuid4().hex[:8]}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO anchor_procedural_guides
                (id, situation, playbook, taboos, confidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (guide_id, situation.strip(), playbook.strip(), taboos.strip(), confidence, now, now)
            )

        logger.info(f"Created procedural guide {guide_id}: {situation[:30]}...")
        return ProceduralGuide(
            id=guide_id,
            situation=situation.strip(),
            playbook=playbook.strip(),
            taboos=taboos.strip(),
            confidence=confidence,
            created_at=now,
            updated_at=now
        )

    def update_guide(
        self,
        guide_id: str,
        playbook: Optional[str] = None,
        taboos: Optional[str] = None
    ) -> Optional[ProceduralGuide]:
        """Update an existing guide's playbook or taboos."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updates = []
        params = []

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
