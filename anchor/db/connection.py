"""Anchor Memory SQLite Database Connection Manager.

Handles schema initialization, context-managed connections,
WAL mode, foreign key enforcement, and persistent settings store.
"""
import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

try:
    from anchor.config import ANCHOR_DB_PATH
except ImportError:
    from config import ANCHOR_DB_PATH

logger = logging.getLogger("anchor.db")

SCHEMA_SQL = """
-- 1. Long-term Memory (episodic, fact, preference, promise, core)
CREATE TABLE IF NOT EXISTS anchor_memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT DEFAULT 'episodic',       -- episodic | fact | preference | promise | core
    importance REAL DEFAULT 0.5,            -- 0.0 ~ 1.0; >= 0.8 enjoys floor protection
    valence REAL DEFAULT 0.0,               -- -1.0 (distressed) ~ +1.0 (joyful)
    arousal REAL DEFAULT 0.0,               -- 0.0 (calm) ~ 1.0 (intense)
    emotion_label TEXT DEFAULT 'neutral',   -- fine-grained emotion tag
    entities TEXT DEFAULT '[]',             -- JSON array of entity strings
    links TEXT DEFAULT '[]',                -- JSON array of related memory IDs
    decay_score REAL DEFAULT 1.0,           -- Ebbinghaus-computed retention weight
    status TEXT DEFAULT 'active',           -- active | superseded | archived
    superseded_by TEXT NULL,
    is_protected INTEGER DEFAULT 0,         -- 1 = hard protection (cannot be auto-superseded/decayed)
    source_message_id TEXT NULL,            -- traceability: which message produced this
    source_date TEXT NULL,                  -- traceability: original dialogue date
    confidence REAL DEFAULT 1.0,            -- extraction confidence
    backfilled INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_am_status ON anchor_memories(status);
CREATE INDEX IF NOT EXISTS idx_am_category ON anchor_memories(category);
CREATE INDEX IF NOT EXISTS idx_am_importance ON anchor_memories(importance);
CREATE INDEX IF NOT EXISTS idx_am_protected ON anchor_memories(is_protected);

-- 2. Memory Notes (non-destructive companion/user annotations)
CREATE TABLE IF NOT EXISTS anchor_memory_notes (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    author TEXT DEFAULT 'companion',        -- 'companion' or 'user'
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES anchor_memories(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_amn_mem_id ON anchor_memory_notes(memory_id);

-- 3. Working Memory (prefrontal cortex short-term buffer)
CREATE TABLE IF NOT EXISTS anchor_working_memory (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT DEFAULT 'general',        -- todo | state | promise | general
    status TEXT DEFAULT 'active',           -- active | expired | archived (no hard delete)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT DEFAULT 'companion',
    expired_at TIMESTAMP NULL,
    expire_reason TEXT NULL,
    archived_at TIMESTAMP NULL,
    auto_clear_after_days INTEGER DEFAULT 2
);
CREATE INDEX IF NOT EXISTS idx_awm_status ON anchor_working_memory(status);

-- 4. Procedural Guides (situation-aware behavior playbooks)
CREATE TABLE IF NOT EXISTS anchor_procedural_guides (
    id TEXT PRIMARY KEY,
    situation TEXT NOT NULL,               -- trigger situation description
    playbook TEXT NOT NULL,                -- best-practice response strategy
    taboos TEXT NOT NULL,                  -- absolute do-not-do list
    confidence REAL DEFAULT 0.8,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Midnight Consolidation Log
CREATE TABLE IF NOT EXISTS anchor_consolidation_log (
    id TEXT PRIMARY KEY,
    consolidation_date TEXT UNIQUE NOT NULL,
    start_message_id TEXT NOT NULL,
    end_message_id TEXT NOT NULL,
    daily_digest TEXT NOT NULL,            -- 500-800 word narrative summary
    wake_note TEXT NOT NULL,               -- morning wake note for next session
    diary_entry_id TEXT NULL,
    memories_created_count INTEGER DEFAULT 0,
    working_memory_updates_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'completed',       -- in_progress | completed | failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Embedding Vector Cache (with model and dimension safety)
CREATE TABLE IF NOT EXISTS anchor_embeddings (
    memory_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    embedding_model TEXT DEFAULT 'local',
    dimension INTEGER DEFAULT 64,
    vector_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Settings Store
CREATE TABLE IF NOT EXISTS anchor_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _configure_connection(conn: sqlite3.Connection) -> None:
    """Enforce WAL mode, foreign keys, and synchronous safety."""
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=10000;")


def init_db(db_path: str = ANCHOR_DB_PATH) -> None:
    """Initialize anchor database directory and schema (safe to call repeatedly)."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10.0) as conn:
        _configure_connection(conn)
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    logger.info(f"Anchor database initialized with WAL and FK enabled at {db_path}")


@contextmanager
def get_db(db_path: str = ANCHOR_DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for SQLite connections with dict-like row access, WAL & FK."""
    path = Path(db_path)
    if not path.exists():
        init_db(db_path)
    conn = sqlite3.connect(db_path, timeout=10.0)
    _configure_connection(conn)
    try:
        from anchor.db.migration import migrate_db
        migrate_db(conn)
    except Exception as me:
        logger.debug(f'Migration hook check: {me}')
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Anchor database error: {e}")
        raise
    finally:
        conn.close()


def get_setting(key: str, default: Any = None, db_path: str = ANCHOR_DB_PATH) -> Any:
    """Retrieve a persisted setting by key, parsing JSON if applicable."""
    try:
        with get_db(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM anchor_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                val_str = row["value"]
                try:
                    return json.loads(val_str)
                except Exception:
                    return val_str
    except Exception as e:
        logger.warning(f"Failed to get anchor setting '{key}': {e}")
    return default


def set_setting(key: str, value: Any, db_path: str = ANCHOR_DB_PATH) -> None:
    """Persist a setting by key, serializing to JSON string."""
    val_str = json.dumps(value) if not isinstance(value, str) else value
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO anchor_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, val_str)
        )


def get_all_settings(db_path: str = ANCHOR_DB_PATH) -> dict:
    """Retrieve all persisted settings as a dictionary."""
    res = {}
    try:
        with get_db(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM anchor_settings")
            for row in cursor.fetchall():
                k = row["key"]
                v_str = row["value"]
                try:
                    res[k] = json.loads(v_str)
                except Exception:
                    res[k] = v_str
    except Exception as e:
        logger.warning(f"Failed to list anchor settings: {e}")
    return res
