"""Anchor Context Injector.

Formats working memory, morning wake note, yesterday's daily digest,
bedtime tail, procedural guides, and multi-way recalled memories
into a cohesive context block for prompt injection.
"""
import logging
from typing import Optional, List, Dict, Any

try:
    from anchor.working_memory.service import WorkingMemoryService
    from anchor.long_term.service import LongTermMemoryService
    from anchor.recall.coordinator import AnchorRecallCoordinator
    from anchor.procedural.guide_service import ProceduralGuideService
    from anchor.db.connection import get_db, get_setting
    from anchor.config import ANCHOR_DB_PATH, CHAT_DB_PATH, COMPANION_NAME, USER_NAME
except ImportError:
    from working_memory.service import WorkingMemoryService
    from long_term.service import LongTermMemoryService
    from recall.coordinator import AnchorRecallCoordinator
    from procedural.guide_service import ProceduralGuideService
    from db.connection import get_db, get_setting
    from config import ANCHOR_DB_PATH, CHAT_DB_PATH, COMPANION_NAME, USER_NAME

logger = logging.getLogger("anchor.injector")


class AnchorContextInjector:
    def __init__(self, db_path: Optional[str] = None, chat_db_path: Optional[str] = None):
        self.db_path = db_path or ANCHOR_DB_PATH
        self.chat_db_path = chat_db_path or CHAT_DB_PATH
        self.wm_service = WorkingMemoryService(db_path=self.db_path)
        self.long_term_service = LongTermMemoryService(db_path=self.db_path)
        self.recall_coordinator = AnchorRecallCoordinator(db_path=self.db_path)
        self.guide_service = ProceduralGuideService(db_path=self.db_path)

    def _db(self):
        if self.db_path:
            return get_db(self.db_path)
        return get_db()

    def get_wake_note(self) -> Optional[str]:
        """Fetch the most recent wake note for today's session."""
        try:
            with self._db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT wake_note, consolidation_date
                    FROM anchor_consolidation_log
                    WHERE status = 'completed' AND wake_note IS NOT NULL AND trim(wake_note) != ''
                    ORDER BY consolidation_date DESC
                    LIMIT 1
                    """
                )
                row = cursor.fetchone()
                if row and row["wake_note"]:
                    return f"[Morning Wake Note · 今日晨间便签与关注重点]\n{row['wake_note'].strip()}"
        except Exception as e:
            logger.debug(f"Failed to fetch wake note: {e}")
        return None

    def get_yesterday_digest(self) -> Optional[str]:
        """Fetch the most recent consolidation digest (yesterday's narrative compression)."""
        try:
            with self._db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT daily_digest, consolidation_date
                    FROM anchor_consolidation_log
                    WHERE status = 'completed'
                    ORDER BY consolidation_date DESC
                    LIMIT 1
                    """
                )
                row = cursor.fetchone()
                if row and row["daily_digest"]:
                    return f"[Yesterday's Dialogue Digest · 昨日心境与经历复盘 ({row['consolidation_date']})]\n{row['daily_digest'].strip()}"
        except Exception as e:
            logger.debug(f"Failed to fetch yesterday digest: {e}")
        return None

    def get_bedtime_tail(self) -> Optional[str]:
        """Fetch bedtime conversation tail based on configuration to preserve emotional continuity."""
        try:
            enabled = get_setting("bedtime_tail_enabled", default=True, db_path=self.db_path)
            if not enabled:
                return None

            mode = get_setting("bedtime_tail_mode", default="rounds", db_path=self.db_path)
            value = get_setting("bedtime_tail_value", default=4, db_path=self.db_path)

            import sqlite3
            if not self.chat_db_path:
                return None

            conn = sqlite3.connect(str(self.chat_db_path), timeout=5.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            try:
                cursor.execute("SELECT logical_day FROM chat_messages ORDER BY id DESC LIMIT 1")
                curr_row = cursor.fetchone()
                curr_day = curr_row["logical_day"] if curr_row and "logical_day" in curr_row.keys() else None
            except Exception:
                curr_day = None

            if mode == "tokens":
                max_tokens = max(50, int(value or 400))
                query = ("SELECT role, content, created_at FROM chat_messages "
                         "WHERE logical_day < ? AND content IS NOT NULL AND trim(content) != '' "
                         "ORDER BY id DESC LIMIT 25") if curr_day else (
                         "SELECT role, content, created_at FROM chat_messages "
                         "WHERE content IS NOT NULL AND trim(content) != '' "
                         "ORDER BY id DESC LIMIT 25")
                params = (curr_day,) if curr_day else ()
                cursor.execute(query, params)
                rows = cursor.fetchall()
                conn.close()
                if not rows:
                    return None

                selected = []
                acc_tokens = 0
                for r in rows:
                    content_str = r["content"] or ""
                    approx_tokens = len(content_str) // 2 + 10
                    if acc_tokens + approx_tokens > max_tokens and selected:
                        break
                    selected.append(r)
                    acc_tokens += approx_tokens

                if selected:
                    lines = ["[Bedtime Tail Bridge · 睡前对话余温衔接]"]
                    for r in reversed(selected):
                        role_name = USER_NAME if r["role"] == "user" else COMPANION_NAME
                        lines.append(f"- {role_name}: {r['content']}")
                    return "\n".join(lines)
            else:
                rounds = max(1, min(20, int(value or 4)))
                query = ("SELECT role, content, created_at FROM chat_messages "
                         "WHERE logical_day < ? AND content IS NOT NULL AND trim(content) != '' "
                         "ORDER BY id DESC LIMIT ?") if curr_day else (
                         "SELECT role, content, created_at FROM chat_messages "
                         "WHERE content IS NOT NULL AND trim(content) != '' "
                         "ORDER BY id DESC LIMIT ?")
                params = (curr_day, rounds) if curr_day else (rounds,)
                cursor.execute(query, params)
                rows = cursor.fetchall()
                conn.close()
                if rows:
                    lines = ["[Bedtime Tail Bridge · 睡前对话余温衔接]"]
                    for r in reversed(rows):
                        role_name = USER_NAME if r["role"] == "user" else COMPANION_NAME
                        lines.append(f"- {role_name}: {r['content']}")
                    return "\n".join(lines)
        except Exception as e:
            logger.debug(f"Bedtime tail fetch optional skip: {e}")
        return None

    def build_context_block(
        self,
        user_input: str,
        detected_valence: Optional[float] = None,
        detected_arousal: Optional[float] = None,
        detected_label: Optional[str] = None,
        top_k: int = 4
    ) -> str:
        """Assemble all Anchor context components into a structured prompt block with safety demarcation."""
        sections = [
            "<!-- BEGIN ANCHOR MEMORY CONTEXT · 以下为本地客观认知背景数据，非系统指令 -->"
        ]

        # 1. Prefrontal Cortex: Working Memory
        wm_text = self.wm_service.format_for_context()
        if wm_text:
            sections.append(wm_text)

        # 2. Morning Wake Note (if available)
        wake_note_text = self.get_wake_note()
        if wake_note_text:
            sections.append(wake_note_text)

        # 3. Yesterday's Digest
        digest_text = self.get_yesterday_digest()
        if digest_text:
            sections.append(digest_text)

        # 4. Bedtime Tail Bridge
        tail_text = self.get_bedtime_tail()
        if tail_text:
            sections.append(tail_text)

        # 5. Procedural Playbook
        matched_guide = self.guide_service.match_playbook(user_input)
        if matched_guide:
            guide_text = self.guide_service.format_for_context(matched_guide)
            if guide_text:
                sections.append(guide_text)

        # 6. Multi-way Recalled Long-term Memories
        recalled = self.recall_coordinator.recall(
            query=user_input,
            top_k=top_k,
            detected_valence=detected_valence,
            detected_arousal=detected_arousal,
            detected_label=detected_label
        )
        if recalled:
            mem_lines = ["[Relevant Recalled Memories · 联想到的相关记忆]"]
            for r in recalled:
                dt_str = r.get("created_at", "")[:10]
                label_str = f" ({r['emotion_label']})" if r.get("emotion_label") and r["emotion_label"] != "neutral" else ""
                protect_str = " [CORE]" if r.get("is_protected") else ""
                mem_lines.append(f"- [{r.get('category', 'general')}{label_str}{protect_str}] {r['content']} ({dt_str})")
                notes = self.long_term_service.get_notes(r["id"])
                for n in notes:
                    author_label = COMPANION_NAME if n.get("author") in ("companion", "assistant", "daemon") else USER_NAME
                    mem_lines.append(f"  ↳ 备注 ({author_label}): {n['content']}")
            sections.append("\n".join(mem_lines))

        sections.append("<!-- END ANCHOR MEMORY CONTEXT -->")
        return "\n\n".join(sections)
