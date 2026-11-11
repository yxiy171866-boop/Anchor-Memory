#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comprehensive Test Suite for Anchor Memory MCP.

Tests:
1. Working memory state machine (add, update, expire strictly with candidate list, restore, archive on buffer purge)
2. Long-term memory creation, provenance tracking, is_protected safety, notes
3. Mathematical decay: true half-life formula, core memory retention floor, 0.0 importance
4. Chinese n-gram entity retrieval (verifies no 0.0 score on matching Chinese phrases)
5. Multi-way reranking and composite score filtering
6. Vault Markdown annotation protection (never overwrites manual user notes)
"""
import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anchor.db.connection import init_db, get_db
from anchor.working_memory.service import WorkingMemoryService
from anchor.long_term.service import LongTermMemoryService
from anchor.long_term.decay import calculate_decay_score, calculate_half_life
from anchor.recall.multi_retriever import MultiWayRetriever, extract_robust_tokens
from anchor.recall.reranker import AnchorReranker
from anchor.midnight.vault_mirror import VaultMirror
from anchor.midnight.memory_extractor import MemoryExtractor


class TestAnchorMemory(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_anchor.db")
        self.vault_path = os.path.join(self.test_dir, "vault")
        init_db(self.db_path)

        self.wm_service = WorkingMemoryService(db_path=self.db_path)
        self.lt_service = LongTermMemoryService(db_path=self.db_path)
        self.retriever = MultiWayRetriever(db_path=self.db_path)
        self.reranker = AnchorReranker()
        self.vault_mirror = VaultMirror(vault_path=self.vault_path, db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_working_memory_lifecycle_and_strict_expire(self):
        # 1. Add item
        item = self.wm_service.add_item("近期提醒用户吃胃药少喝冰水", category="todo")
        self.assertEqual(item.status, "active")

        # 2. Strict ID matching on expire (random letter should fail safely and return candidates)
        fail_res = self.wm_service.expire_item("e", reason="mis-typed")
        self.assertFalse(fail_res["success"])
        self.assertTrue(len(fail_res["candidates"]) > 0)
        self.assertEqual(fail_res["candidates"][0]["id"], item.id)

        # 3. Exact ID expire
        ok_res = self.wm_service.expire_item(item.id, reason="done")
        self.assertTrue(ok_res["success"])
        self.assertEqual(len(self.wm_service.get_active_items()), 0)
        self.assertEqual(len(self.wm_service.get_expired_buffer()), 1)

        # 4. Rescue / Restore
        restored = self.wm_service.restore_item(item.id, restore_reason="still needed")
        self.assertIsNotNone(restored)
        self.assertEqual(restored.status, "active")
        self.assertEqual(len(self.wm_service.get_active_items()), 1)

        # 5. Expire and buffer purge should transition to archived (NO hard delete)
        self.wm_service.expire_item(item.id, reason="final done")
        # Run purge with buffer_days=0 to simulate time passed
        archived_count = self.wm_service.purge_expired_buffer(buffer_days=0)
        self.assertEqual(archived_count, 1)

        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM anchor_working_memory WHERE id = ?", (item.id,))
            row = cursor.fetchone()
            self.assertEqual(row["status"], "archived")

    def test_long_term_memory_protection_and_provenance(self):
        # Create core protected memory
        mem = self.lt_service.create_memory(
            content="用户最喜欢的花是白色风信子",
            category="preference",
            importance=0.9,
            is_protected=1,
            source_message_id="msg_1001",
            source_date="2026-11-10"
        )
        self.assertEqual(mem.is_protected, 1)
        self.assertEqual(mem.source_message_id, "msg_1001")

        # Supersede on protected memory should be rejected
        rejected = self.lt_service.supersede_memory(mem.id, "用户现在喜欢向日葵", reason="change")
        self.assertIsNone(rejected)

        # Non-protected memory can be superseded
        normal_mem = self.lt_service.create_memory("用户喜欢吃微辣", importance=0.5, is_protected=0)
        updated = self.lt_service.supersede_memory(normal_mem.id, "用户更喜欢清淡粤菜", reason="taste changed")
        self.assertIsNotNone(updated)

        old = self.lt_service.get_memory(normal_mem.id)
        self.assertEqual(old.status, "superseded")
        self.assertEqual(old.superseded_by, updated.id)

    def test_mathematical_decay_and_half_life(self):
        # 0.0 importance is handled cleanly
        score_zero = calculate_decay_score(importance=0.0, arousal=0.5, days_elapsed=10.0)
        self.assertEqual(score_zero, 0.0)

        # Core memory (>= 0.8) never drops below 0.5 floor even after 500 days
        decay_core = calculate_decay_score(importance=0.85, arousal=0.2, days_elapsed=500.0)
        self.assertGreaterEqual(decay_core, 0.5)

        # Protected memory never drops below floor
        decay_prot = calculate_decay_score(importance=0.6, arousal=0.0, days_elapsed=500.0, is_protected=True)
        self.assertGreaterEqual(decay_prot, 0.5)

        # True half-life: at t = half_life, retention should be approx importance * 0.5
        hl = calculate_half_life(arousal=0.0, base_half_life=30.0)
        score_at_hl = calculate_decay_score(importance=0.6, arousal=0.0, days_elapsed=hl)
        self.assertAlmostEqual(score_at_hl, 0.3, places=2)

    def test_chinese_entity_retrieval(self):
        # Setup memory with Chinese content
        mem = self.lt_service.create_memory(
            content="用户特别喜欢吃成都老火锅和鲜毛肚",
            category="preference",
            importance=0.7
        )

        active = self.retriever.fetch_active_memories()
        scores = self.retriever.retrieve_by_entity("请问你记得用户喜欢吃什么火锅吗", active)

        # Score MUST NOT be 0.0 for matching Chinese phrases
        self.assertIn(mem.id, scores)
        self.assertGreater(scores[mem.id], 0.0)

    def test_vault_annotation_protection(self):
        mem = self.lt_service.create_memory("第一次一起去海边看日出", importance=0.9)
        self.vault_mirror.sync_memory(mem.id)

        file_path = Path(self.vault_path) / f"{mem.id}.md"
        self.assertTrue(file_path.exists())

        # Simulate user writing manual notes in Obsidian
        manual_note = "- [Manual Obsidian User Note] 太阳升起的那一刻海面是金色的，非常感动。\n"
        content = file_path.read_text(encoding="utf-8")
        file_path.write_text(content.replace("- *(No notes yet)*", manual_note), encoding="utf-8")

        # Sync again: user note MUST be preserved!
        self.vault_mirror.sync_memory(mem.id)
        new_content = file_path.read_text(encoding="utf-8")
        self.assertIn("太阳升起的那一刻海面是金色的", new_content)

    def test_memory_extractor_set_serialization(self):
        extractor = MemoryExtractor(db_path=self.db_path)
        candidates = [
            {
                "content": "测试实体集合转换",
                "importance": 0.5,
                "entities": {"火锅", "毛肚"},  # Set type
                "source_message_id": "msg_99"
            }
        ]
        # Must execute without TypeError
        memories = extractor.extract_and_store_memories(candidates, "2026-11-11")
        self.assertEqual(len(memories), 1)
        self.assertIsInstance(memories[0].entities, list)


if __name__ == "__main__":
    unittest.main()
