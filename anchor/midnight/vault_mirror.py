"""Anchor Midnight Step 6 - Obsidian Vault Mirror (Incremental Sync).

Writes long-term memories as Markdown files to a local vault directory
compatible with Obsidian or any Markdown-based note system.
"""
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

try:
    from anchor.config import ANCHOR_VAULT_PATH, ANCHOR_DB_PATH
    from anchor.db.connection import get_db
except ImportError:
    from config import ANCHOR_VAULT_PATH, ANCHOR_DB_PATH
    from db.connection import get_db

logger = logging.getLogger("anchor.midnight.vault")


class VaultMirror:
    def __init__(self, vault_path: Optional[str] = None, db_path: Optional[str] = None):
        self.vault_path = Path(vault_path or ANCHOR_VAULT_PATH)
        self.db_path = db_path or ANCHOR_DB_PATH

    def _db(self):
        return get_db(self.db_path)

    def _memory_to_markdown(self, mem: Dict[str, Any], notes: List[Dict[str, Any]]) -> str:
        """Render a memory dict as a Markdown document."""
        lines = [
            f"---",
            f"id: {mem['id']}",
            f"category: {mem.get('category', 'general')}",
            f"importance: {mem.get('importance', 0.5)}",
            f"valence: {mem.get('valence', 0.0)}",
            f"arousal: {mem.get('arousal', 0.0)}",
            f"emotion: {mem.get('emotion_label', 'neutral')}",
            f"decay_score: {round(float(mem.get('decay_score', 1.0)), 4)}",
            f"created_at: {mem.get('created_at', '')[:10]}",
            f"status: {mem.get('status', 'active')}",
            f"---",
            f"",
            f"# Memory",
            f"",
            mem.get("content", ""),
            f"",
        ]

        entities = mem.get("entities")
        if isinstance(entities, str):
            try:
                entities = json.loads(entities)
            except Exception:
                entities = []
        if entities:
            lines.append(f"**Entities:** {', '.join(entities)}")
            lines.append("")

        if notes:
            lines.append("## Notes")
            for note in notes:
                author = note.get("author", "unknown")
                created = note.get("created_at", "")[:10]
                content = note.get("content", "")
                lines.append(f"- **[{author}]** ({created}): {content}")
            lines.append("")

        return "\n".join(lines)

    def sync_memory(self, memory_id: str) -> bool:
        """Write a single memory to the vault as a Markdown file."""
        self.vault_path.mkdir(parents=True, exist_ok=True)

        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM anchor_memories WHERE id = ?", (memory_id,))
            row = cursor.fetchone()
            if not row:
                return False
            mem = dict(row)

            cursor.execute(
                "SELECT * FROM anchor_memory_notes WHERE memory_id = ? ORDER BY created_at ASC",
                (memory_id,)
            )
            notes = [dict(r) for r in cursor.fetchall()]

        content = self._memory_to_markdown(mem, notes)
        safe_name = memory_id.replace("/", "_").replace("\\", "_")
        file_path = self.vault_path / f"{safe_name}.md"

        try:
            file_path.write_text(content, encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to write vault file for {memory_id}: {e}")
            return False

    def sync_all_active(self) -> int:
        """Sync all active memories to vault. Returns count synced."""
        with self._db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM anchor_memories WHERE status = 'active'")
            ids = [r["id"] for r in cursor.fetchall()]

        count = 0
        for mem_id in ids:
            if self.sync_memory(mem_id):
                count += 1

        logger.info(f"Vault sync complete: {count}/{len(ids)} memories written.")
        return count

    def write_consolidation_log(self, date_str: str, digest: str, wake_note: str) -> bool:
        """Write the nightly consolidation summary to the vault."""
        self.vault_path.mkdir(parents=True, exist_ok=True)
        log_dir = self.vault_path / "consolidation_logs"
        log_dir.mkdir(exist_ok=True)

        content = f"---\ndate: {date_str}\ntype: consolidation_log\n---\n\n"
        content += f"# Daily Digest ({date_str})\n\n{digest}\n\n"
        content += f"# Morning Wake Note\n\n{wake_note}\n"

        try:
            (log_dir / f"{date_str}.md").write_text(content, encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to write consolidation log for {date_str}: {e}")
            return False
