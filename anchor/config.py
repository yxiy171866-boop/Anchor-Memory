"""Anchor Memory System - Global Configuration.

All paths can be overridden via environment variables.
No hardcoded machine-specific paths.
"""
from pathlib import Path
import os

# Base paths (relative to this file)
ANCHOR_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ANCHOR_DIR.parent

# Database path — override with ANCHOR_DB_PATH env var
ANCHOR_DB_PATH = os.getenv(
    "ANCHOR_DB_PATH",
    str(PROJECT_ROOT / "data" / "anchor_memory.db")
)

# Obsidian Vault mirror path — override with ANCHOR_VAULT_PATH env var
ANCHOR_VAULT_PATH = os.getenv(
    "ANCHOR_VAULT_PATH",
    str(PROJECT_ROOT / "anchor_vault")
)

# Search tool mode: 'always' | 'never' | 'on_demand' (default: on_demand)
ANCHOR_SEARCH_TOOL_MODE = os.getenv("ANCHOR_SEARCH_TOOL_MODE", "on_demand")

# Working Memory Configuration
WORKING_MEMORY_BUFFER_DAYS = int(os.getenv("ANCHOR_WM_BUFFER_DAYS", "2"))

# Ebbinghaus Decay Configuration
DECAY_BASE_HALF_LIFE_DAYS = float(os.getenv("ANCHOR_DECAY_BASE_HALF_LIFE", "30.0"))
DECAY_AROUSAL_MULTIPLIER = float(os.getenv("ANCHOR_DECAY_AROUSAL_K", "3.0"))
CORE_MEMORY_IMPORTANCE_THRESHOLD = float(os.getenv("ANCHOR_CORE_IMPORTANCE_THRESHOLD", "0.8"))
CORE_MEMORY_FLOOR_WEIGHT = 0.5

# Multi-way Recall Weights (Rerank)
RECALL_WEIGHT_SEMANTIC = 0.55
RECALL_WEIGHT_ENTITY = 0.25
RECALL_WEIGHT_EMOTION = 0.10
RECALL_WEIGHT_RECENCY = 0.10
RECALL_TOP_K = int(os.getenv("ANCHOR_RECALL_TOP_K", "4"))
RECALL_MIN_SCORE_THRESHOLD = float(os.getenv("ANCHOR_RECALL_MIN_THRESHOLD", "0.30"))

# Midnight Consolidation Configuration
MIDNIGHT_INACTIVITY_MINUTES = int(os.getenv("ANCHOR_MIDNIGHT_INACTIVITY_MIN", "90"))
MIDNIGHT_SUMMARY_MIN_WORDS = 500
MIDNIGHT_SUMMARY_MAX_WORDS = 800

# Legacy Backfill Configuration (optional migration from older memory formats)
AM_BACKFILL_ENABLED = os.getenv("ANCHOR_AM_BACKFILL_ENABLED", "true").lower() in ("true", "1", "yes")
AM_BACKFILL_BATCH_SIZE = int(os.getenv("ANCHOR_AM_BACKFILL_BATCH_SIZE", "10"))
FALLBACK_NEUTRAL_VALENCE = 0.5
FALLBACK_NEUTRAL_AROUSAL = 0.5

# Persona configuration (used in tool descriptions and consolidation prompts)
# Set these to fit your AI companion's identity
COMPANION_NAME = os.getenv("ANCHOR_COMPANION_NAME", "companion")
USER_NAME = os.getenv("ANCHOR_USER_NAME", "user")

# Chat database path (used by midnight consolidation to read conversation history)
# Point this to wherever your chat application stores its SQLite messages.
CHAT_DB_PATH = os.getenv(
    "ANCHOR_CHAT_DB_PATH",
    str(PROJECT_ROOT / "data" / "chat.db")
)
