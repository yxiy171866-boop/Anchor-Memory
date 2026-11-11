"""Database Schema Migration Helper for Anchor Memory.

Ensures that older database schemas are safely and non-destructively
upgraded to the latest version by adding missing columns and tables.
"""
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger("anchor.migration")


def migrate_db(conn: sqlite3.Connection) -> None:
    """Check existing tables and add any missing columns safely."""
    cursor = conn.cursor()

    # 1. Check anchor_memories columns
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='anchor_memories'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(anchor_memories)")
        cols = set(r[1] for r in cursor.fetchall())

        missing = {
            "is_protected": "INTEGER DEFAULT 0",
            "source_message_id": "TEXT NULL",
            "source_date": "TEXT NULL",
            "confidence": "REAL DEFAULT 1.0",
            "backfilled": "INTEGER DEFAULT 0",
        }

        for col_name, col_def in missing.items():
            if col_name not in cols:
                logger.info(f"Migrating anchor_memories: adding missing column '{col_name}'")
                cursor.execute(f"ALTER TABLE anchor_memories ADD COLUMN {col_name} {col_def}")

    # 2. Check anchor_working_memory columns
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='anchor_working_memory'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(anchor_working_memory)")
        cols = set(r[1] for r in cursor.fetchall())

        if "archived_at" not in cols:
            logger.info("Migrating anchor_working_memory: adding missing column 'archived_at'")
            cursor.execute("ALTER TABLE anchor_working_memory ADD COLUMN archived_at TIMESTAMP NULL")

    # 3. Check anchor_embeddings columns
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='anchor_embeddings'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(anchor_embeddings)")
        cols = set(r[1] for r in cursor.fetchall())

        if "embedding_model" not in cols:
            cursor.execute("ALTER TABLE anchor_embeddings ADD COLUMN embedding_model TEXT DEFAULT 'local'")
        if "dimension" not in cols:
            cursor.execute("ALTER TABLE anchor_embeddings ADD COLUMN dimension INTEGER DEFAULT 64")

    conn.commit()
