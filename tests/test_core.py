#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comprehensive Test Suite for Anchor Memory MCP."""
import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anchor.db.connection import init_db, get_db
from anchor.working_memory.service import WorkingMemoryService
from anchor.long_term.service import LongTermMemoryService
from anchor.long_term.decay import calculate_decay_score, calculate_half_life
from anchor.recall.multi_retriever import MultiWayRetriever
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
        item = self.wm_service.add_item("近期提醒用户吃胃药少喝冰水", category="todo")
        self.assertEqual(item.status, "active")

        # Strict ID match
        fail_res = self.wm_service.expire_item("e", reason="mis-typed")
        self.assertFalse(fail_res["success"])
        self.assertTrue(len(fail_res["candidates"]) > 0)

        # Exact ID
        ok_res = self.wm_service.expire_item(item.id, reason="done")
        self.assertTrue(ok_res["success"])
        self.assertEqual(len(self.wm_service.get_active_items()), 0)

        # Restore
        restored = self.wm_service.restore_item(item.id, restore_reason="still needed")
        self.assertIsNotNone(restored)
        self.assertEqual(restored.status, "active")

        # Expire & Archive
        self.wm_service.expire_item(item.id, reason="final done")
        archived_count = self.wm_service.purge_expired_buffer(buffer_days=0)
        self.assertEqual(archived_count, 1)

    def test_long_term_memory_protection_and_provenance(self):
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

        # Reject supersede on protected
        rejected = self.lt_service.supersede_memory(mem.id, "用户现在喜欢向日葵", reason="change")
        self.assertIsNone(rejected)

    def test_mathematical_decay_and_half_life(self):
        score_zero = calculate_decay_score(importance=0.0, arousal=0.5, days_elapsed=10.0)
        self.assertEqual(score_zero, 0.0)

        decay_core = calculate_decay_score(importance=0.85, arousal=0.2, days_elapsed=500.0)
        self.assertGreaterEqual(decay_core, 0.5)

        hl = calculate_half_life(arousal=0.0, base_half_life=30.0)
        score_at_hl = calculate_decay_score(importance=0.6, arousal=0.0, days_elapsed=hl)
        self.assertAlmostEqual(score_at_hl, 0.3, places=2)

    def test_chinese_entity_retrieval(self):
        mem = self.lt_service.create_memory("用户特别喜欢吃成都老火锅和鲜毛肚", importance=0.7)
        active = self.retriever.fetch_active_memories()
        scores = self.retriever.retrieve_by_entity("请问你记得用户喜欢吃什么火锅吗", active)
        self.assertIn(mem.id, scores)
        self.assertGreater(scores[mem.id], 0.0)

    def test_vault_annotation_protection(self):
        mem = self.lt_service.create_memory("第一次一起去海边看日出", importance=0.9)
        self.vault_mirror.sync_memory(mem.id)

        file_path = Path(self.vault_path) / f"{mem.id}.md"
        self.assertTrue(file_path.exists())

        # Simulate user writing manual notes in Obsidian under ## User Notes
        content = file_path.read_text(encoding="utf-8")
        custom_note = "太阳升起的那一刻海面是金色的，非常感动。"
        file_path.write_text(content.replace("<!-- Add your private manual annotations here; they will never be overwritten. -->", custom_note), encoding="utf-8")

        # Sync again: user note MUST be preserved!
        self.vault_mirror.sync_memory(mem.id)
        new_content = file_path.read_text(encoding="utf-8")
        self.assertIn("太阳升起的那一刻海面是金色的", new_content)

    def test_memory_extractor_set_serialization(self):
        extractor = MemoryExtractor(db_path=self.db_path)
        candidates = [{"content": "测试实体集合转换", "importance": 0.5, "entities": {"火锅", "毛肚"}}]
        memories = extractor.extract_and_store_memories(candidates, "2026-11-11")
        self.assertEqual(len(memories), 1)
        self.assertIsInstance(memories[0].entities, list)

    def test_legacy_db_schema_migration(self):
        old_db_path = os.path.join(self.test_dir, "old_anchor.db")
        import sqlite3
        conn = sqlite3.connect(old_db_path)
        conn.execute("""
            CREATE TABLE anchor_memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'episodic',
                importance REAL DEFAULT 0.5,
                valence REAL DEFAULT 0.0,
                arousal REAL DEFAULT 0.0,
                emotion_label TEXT DEFAULT 'neutral',
                entities TEXT DEFAULT '[]',
                links TEXT DEFAULT '[]',
                decay_score REAL DEFAULT 1.0,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        conn.close()

        old_lt = LongTermMemoryService(db_path=old_db_path)
        old_lt.create_memory("老数据库升级兼容测试", is_protected=1)
        active = old_lt.get_all_active()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].is_protected, 1)

    def test_search_conversation_tuple_unpack(self):
        chat_db_path = os.path.join(self.test_dir, "chat.db")
        import sqlite3
        conn = sqlite3.connect(chat_db_path)
        conn.execute("""
            CREATE TABLE chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("INSERT INTO chat_messages (role, content) VALUES ('user', '今天天气真好一起去散步吧')")
        conn.commit()
        conn.close()

        from anchor.recall.chat_history import ConversationSearchTool
        cs_tool = ConversationSearchTool(chat_db_path=chat_db_path)
        res = cs_tool.search_conversation(query="天气散步")
        self.assertNotIn("error", res)
        self.assertEqual(res["count"], 1)

    def test_working_memory_auditor_dict_result_check(self):
        from anchor.midnight.working_memory_auditor import WorkingMemoryAuditor
        auditor = WorkingMemoryAuditor(db_path=self.db_path)
        res = auditor.audit_and_purge(resolved_items=[{"id": "non_existent_id", "reason": "test"}])
        self.assertEqual(res["expired_count"], 0)

    def test_procedural_guide_deduplication_and_delete(self):
        from anchor.procedural.guide_service import ProceduralGuideService
        svc = ProceduralGuideService(db_path=self.db_path)
        g1 = svc.create_guide(
            situation="when user is feeling anxious about work",
            playbook="listen gently and validate feelings",
            taboos="never say 'just calm down'"
        )
        self.assertFalse(getattr(g1, "_is_updated", False))

        # Similar situation should be deduplicated and merged
        g2 = svc.create_guide(
            situation="when user feels anxious",
            playbook="stay present and offer a hug",
            taboos="avoid lecturing"
        )
        self.assertEqual(g1.id, g2.id)
        self.assertTrue(getattr(g2, "_is_updated", False))
        self.assertIn("listen gently", g2.playbook)
        self.assertIn("stay present", g2.playbook)

        # Deletion
        ok = svc.delete_guide(g1.id)
        self.assertTrue(ok)
        self.assertEqual(len(svc.get_all_guides()), 0)

    def test_working_memory_buffer_context_injection_and_countdown(self):
        from anchor.working_memory.service import WorkingMemoryService
        wm = WorkingMemoryService(db_path=self.db_path)
        item1 = wm.add_item("Active task: prepare presentation", category="todo")
        item2 = wm.add_item("Completed task: fix bug in auth", category="task")
        
        # Expire item2 into buffer
        wm.expire_item(item2.id, reason="fixed in commit 123")
        
        context_text = wm.format_for_context()
        self.assertIn("Active Items (In Progress)", context_text)
        self.assertIn(item1.id, context_text)
        self.assertIn("Expired Buffer", context_text)
        self.assertIn(item2.id, context_text)
        self.assertIn("until archive", context_text)
        self.assertIn("fixed in commit 123", context_text)


if __name__ == "__main__":
    unittest.main()
