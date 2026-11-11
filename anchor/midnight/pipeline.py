"""Anchor Midnight Master Consolidation Pipeline.

Executes the complete nightly consolidation flow:
Step 1: Daily Dialogue Compression (500-800 words in companion voice)
Step 2: Long-Term Memory Extraction with Emotional Coordinates
Step 3: Working Memory Prefrontal Audit & 2-day Buffer Purge
Step 4: Morning Wake Note Generation
Step 5: (Optional) Diary Integration — wire up your own diary module here
Step 6: Obsidian Vault Mirror Incremental Sync

Plus:
- Configurable Legacy Backfill Batch Engine
- Daily Ebbinghaus Decay Recalculation
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

try:
    from anchor.config import (
        ANCHOR_DB_PATH,
        ANCHOR_VAULT_PATH,
        AM_BACKFILL_ENABLED,
        AM_BACKFILL_BATCH_SIZE,
    )
    from anchor.midnight.dialogue_compressor import DialogueCompressor
    from anchor.midnight.memory_extractor import MemoryExtractor
    from anchor.midnight.working_memory_auditor import WorkingMemoryAuditor
    from anchor.midnight.wake_note_generator import WakeNoteGenerator
    from anchor.midnight.vault_mirror import VaultMirror
    from anchor.long_term.service import LongTermMemoryService
    from anchor.long_term.backfill_service import AnchorBackfillService
    from anchor.working_memory.service import WorkingMemoryService
    from anchor.db.connection import get_db
except ImportError:
    from config import (
        ANCHOR_DB_PATH,
        ANCHOR_VAULT_PATH,
        AM_BACKFILL_ENABLED,
        AM_BACKFILL_BATCH_SIZE,
    )
    from midnight.dialogue_compressor import DialogueCompressor
    from midnight.memory_extractor import MemoryExtractor
    from midnight.working_memory_auditor import WorkingMemoryAuditor
    from midnight.wake_note_generator import WakeNoteGenerator
    from midnight.vault_mirror import VaultMirror
    from long_term.service import LongTermMemoryService
    from long_term.backfill_service import AnchorBackfillService
    from working_memory.service import WorkingMemoryService
    from db.connection import get_db

logger = logging.getLogger("anchor.midnight.pipeline")


class MidnightPipeline:
    def __init__(
        self,
        db_path: Optional[str] = None,
        vault_path: Optional[str] = None
    ):
        self.db_path = db_path or ANCHOR_DB_PATH
        self.vault_path = vault_path or ANCHOR_VAULT_PATH

        self.compressor = DialogueCompressor(db_path=self.db_path)
        self.extractor = MemoryExtractor(db_path=self.db_path)
        self.wm_auditor = WorkingMemoryAuditor(db_path=self.db_path)
        self.wake_generator = WakeNoteGenerator(db_path=self.db_path)
        self.vault_mirror = VaultMirror(vault_path=self.vault_path, db_path=self.db_path)

        self.lt_service = LongTermMemoryService(db_path=self.db_path)
        self.wm_service = WorkingMemoryService(db_path=self.db_path)
        self.backfill_service = AnchorBackfillService(db_path=self.db_path)

    def run_midnight_consolidation(
        self,
        target_date: Optional[str] = None,
        custom_narrative: Optional[str] = None,
        candidate_memories: Optional[List[Dict[str, Any]]] = None,
        resolved_wm_items: Optional[List[Dict[str, str]]] = None,
        new_commitments: Optional[List[Dict[str, str]]] = None,
        backfill_override: Optional[bool] = None,
        backfill_batch_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """Run the end-to-end nightly consolidation pipeline.

        Args:
            target_date: Date to consolidate (default: today, format YYYY-MM-DD)
            custom_narrative: Pre-generated AI narrative for Step 1 (optional)
            candidate_memories: Memory items to extract (from AI, optional)
            resolved_wm_items: Working memory items to expire (list of {id, reason})
            new_commitments: New WM items to add (list of {content, category})
            backfill_override: Override AM_BACKFILL_ENABLED setting
            backfill_batch_size: Override AM_BACKFILL_BATCH_SIZE setting

        Returns:
            Summary dict with counts and status for each pipeline step.
        """
        date_str = target_date or datetime.now().strftime("%Y-%m-%d")
        logger.info(f"Starting Anchor Midnight Consolidation for {date_str}...")

        result = {
            "date": date_str,
            "steps": {},
            "success": False,
        }

        # Step 1: Fetch and Compress Dialogue
        messages = self.compressor.fetch_day_messages(date_str)
        daily_digest = self.compressor.compress_dialogue(
            messages=messages,
            target_date=date_str,
            custom_narrative=custom_narrative
        )
        result["steps"]["1_dialogue_compression"] = {
            "messages_count": len(messages),
            "digest_length": len(daily_digest),
        }

        # Step 2: Extract Long-Term Memories
        extracted_memories = []
        if candidate_memories:
            extracted_memories = self.extractor.extract_and_store_memories(
                candidate_items=candidate_memories,
                date_str=date_str
            )
        result["steps"]["2_memory_extraction"] = {
            "memories_created": len(extracted_memories),
        }

        # Step 3: Working Memory Audit
        wm_result = self.wm_auditor.audit_and_purge(
            resolved_items=resolved_wm_items,
            new_items=new_commitments,
        )
        result["steps"]["3_wm_audit"] = wm_result

        # Step 4: Morning Wake Note
        wake_note = self.wake_generator.generate_wake_note(
            daily_digest=daily_digest,
            target_date=date_str,
        )
        result["steps"]["4_wake_note"] = {"length": len(wake_note)}

        # Step 5: Optional diary integration hook
        # To integrate your own diary system, subclass MidnightPipeline
        # and override this step.
        result["steps"]["5_diary"] = {"status": "skipped (optional module)"}

        # Step 6: Vault Sync
        synced = self.vault_mirror.sync_all_active()
        self.vault_mirror.write_consolidation_log(date_str, daily_digest, wake_note)
        result["steps"]["6_vault_sync"] = {"memories_synced": synced}

        # Bonus: Legacy Backfill Batch (if enabled)
        do_backfill = backfill_override if backfill_override is not None else AM_BACKFILL_ENABLED
        if do_backfill:
            batch_size = backfill_batch_size or AM_BACKFILL_BATCH_SIZE
            try:
                bf_result = self.backfill_service.backfill_batch(limit=batch_size)
                result["steps"]["backfill"] = bf_result
            except Exception as e:
                logger.warning(f"Backfill skipped: {e}")
                result["steps"]["backfill"] = {"status": "skipped", "error": str(e)}

        # Save consolidation log to DB
        try:
            self._save_consolidation_log(date_str, daily_digest, wake_note, extracted_memories)
        except Exception as e:
            logger.warning(f"Failed to save consolidation log to DB: {e}")

        # Recalculate all decay scores
        decay_updated = self.lt_service.recalculate_all_decay_scores()
        result["steps"]["decay_recalc"] = {"updated": decay_updated}

        result["success"] = True
        logger.info(f"Midnight consolidation complete for {date_str}.")
        return result

    def _save_consolidation_log(
        self,
        date_str: str,
        daily_digest: str,
        wake_note: str,
        extracted_memories: list
    ) -> None:
        """Persist consolidation summary to anchor_consolidation_log table."""
        import uuid
        log_id = f"consolidation_{date_str}_{uuid.uuid4().hex[:6]}"

        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO anchor_consolidation_log
                (id, consolidation_date, start_message_id, end_message_id,
                 daily_digest, wake_note, memories_created_count, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'completed')
                """,
                (log_id, date_str, "auto", "auto",
                 daily_digest, wake_note, len(extracted_memories))
            )
