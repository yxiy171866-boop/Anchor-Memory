#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Anchor Memory MCP Server.

A local-first long-term memory system for AI companions.
Provides 12 focused tools covering working memory, episodic/semantic
long-term memory, situation-aware procedural guides, and conversation history search.

Usage:
    python server.py

Configuration (via environment variables):
    ANCHOR_DB_PATH          Path to SQLite database (default: ./data/anchor_memory.db)
    ANCHOR_VAULT_PATH       Path to Obsidian vault mirror (default: ./anchor_vault)
    ANCHOR_COMPANION_NAME   Name of the AI companion (default: companion)
    ANCHOR_USER_NAME        Name of the human user (default: user)
    ANCHOR_SEARCH_TOOL_MODE Search mode: always | never | on_demand (default: on_demand)
    ANCHOR_CHAT_DB_PATH     Path to chat SQLite database for conversation search
"""
import sys
import logging
from typing import Optional, List

from mcp.server.mcpserver import MCPServer

try:
    from anchor.working_memory.service import WorkingMemoryService
    from anchor.long_term.service import LongTermMemoryService
    from anchor.recall.search_tool import AnchorSearchTool
    from anchor.recall.chat_history import ConversationSearchTool
    from anchor.procedural.guide_service import ProceduralGuideService
    from anchor.config import ANCHOR_DB_PATH, COMPANION_NAME, USER_NAME
except ImportError:
    from working_memory.service import WorkingMemoryService
    from long_term.service import LongTermMemoryService
    from recall.search_tool import AnchorSearchTool
    from recall.chat_history import ConversationSearchTool
    from procedural.guide_service import ProceduralGuideService
    from config import ANCHOR_DB_PATH, COMPANION_NAME, USER_NAME

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("anchor.server")

mcp = MCPServer("anchor_memory")

wm_service = WorkingMemoryService()
lt_service = LongTermMemoryService()
search_tool = AnchorSearchTool()
conv_search_tool = ConversationSearchTool()
guide_service = ProceduralGuideService()

# ----------------- 1. Working Memory Tools -----------------

@mcp.tool()
async def working_memory_add(content: str, category: str = "general") -> str:
    """Add a short-term ongoing item to working memory (prefrontal buffer).

    Use this for tasks, commitments, or situations that need active attention
    over the next few days. Items expire automatically after the buffer period.

    Parameters:
    - content: Description of the ongoing item or status to track
    - category: One of 'todo' | 'state' | 'promise' | 'general'
    """
    item = wm_service.add_item(content=content, category=category)
    return f"Added to working memory [{item.id}]: {item.content} (category: {item.category})"


@mcp.tool()
async def working_memory_update(item_id: str, content: str) -> str:
    """Update progress or details for an existing working memory item.

    Parameters:
    - item_id: Item ID (e.g. 'wm_20261109_xxxx')
    - content: Updated description or latest progress
    """
    ok = wm_service.update_item(item_id=item_id, content=content)
    if ok:
        return f"Updated working memory item [{item_id}]: {content}"
    return f"Update failed: item [{item_id}] not found."


@mcp.tool()
async def working_memory_expire(item_id: str, reason: str = "resolved") -> str:
    """Mark a working memory item as resolved/expired.

    Items enter a 2-day buffer period before permanent deletion,
    allowing recovery in case of false positives.

    Parameters:
    - item_id: Item ID
    - reason: Why this item is being resolved or expired
    """
    ok = wm_service.expire_item(item_id=item_id, reason=reason)
    if ok:
        return (f"Item [{item_id}] marked as expired and moved to 2-day buffer "
                f"(reason: {reason}). Call working_memory_restore if this was a mistake.")
    return f"Expire failed: active item [{item_id}] not found."


@mcp.tool()
async def working_memory_restore(item_id: str, restore_reason: str = "false positive recovery") -> str:
    """Restore an expired working memory item back to active status.

    Parameters:
    - item_id: ID of item in the expiry buffer
    - restore_reason: Reason for restoration
    """
    item = wm_service.restore_item(item_id=item_id, restore_reason=restore_reason)
    if item:
        return f"Restored! Item [{item.id}] is active again (reason: {restore_reason})."
    return f"Restore failed: item [{item_id}] not found or already past buffer period."


# ----------------- 2. Long-term Memory Tools -----------------

@mcp.tool()
async def memory_create(
    content: str,
    category: str = "episodic",
    importance: float = 0.6,
    valence: float = 0.0,
    arousal: float = 0.0,
    emotion_label: str = "neutral",
    entities: Optional[List[str]] = None,
    links: Optional[List[str]] = None
) -> str:
    """Create a long-term memory with emotional coordinates.

    Use this to persist significant life events, facts, preferences, or
    commitments that should be remembered across sessions.

    Parameters:
    - content: Memory content
    - category: 'episodic' | 'fact' | 'preference' | 'promise' | 'core'
    - importance: 0.0~1.0 (>= 0.8 receives permanent floor protection against decay)
    - valence: Emotional valence (-1.0 negative ~ +1.0 positive)
    - arousal: Emotional intensity (0.0 calm ~ 1.0 intense)
    - emotion_label: Fine-grained emotion tag (e.g. 'joy', 'comfort', 'grief')
    - entities: Key person/place/thing entities mentioned
    - links: Related memory IDs
    """
    mem = lt_service.create_memory(
        content=content,
        category=category,
        importance=importance,
        valence=valence,
        arousal=arousal,
        emotion_label=emotion_label,
        entities=entities or [],
        links=links or []
    )
    return f"Long-term memory created [{mem.id}] (category: {mem.category}, importance: {mem.importance}, emotion: {mem.emotion_label})"


@mcp.tool()
async def memory_update(memory_id: str, content: str) -> str:
    """Correct or update the text of an existing long-term memory.

    Parameters:
    - memory_id: Memory ID
    - content: Corrected memory text
    """
    ok = lt_service.update_memory(memory_id=memory_id, mode="replace", content=content)
    if ok:
        return f"Memory [{memory_id}] updated successfully."
    return f"Update failed: memory [{memory_id}] not found."


@mcp.tool()
async def memory_add_note(memory_id: str, content: str) -> str:
    """Append a note or reflection to an existing memory without altering original text.

    Parameters:
    - memory_id: Long-term memory ID
    - content: Supplementary reflection, follow-up, or new insight
    """
    note = lt_service.add_note(memory_id=memory_id, author="companion", content=content)
    if note:
        return f"Note [{note['id']}] appended to memory [{memory_id}]: {content}"
    return f"Failed to add note: memory [{memory_id}] not found."


@mcp.tool()
async def memory_supersede(old_memory_id: str, new_content: str, reason: str) -> str:
    """Replace an outdated memory with an updated version.

    The old memory is preserved as a 'superseded' historical record.

    Parameters:
    - old_memory_id: ID of the memory to be replaced
    - new_content: Updated fact, preference, or event description
    - reason: Why this memory is being updated (what changed)
    """
    new_mem = lt_service.supersede_memory(
        old_memory_id=old_memory_id, new_content=new_content, reason=reason
    )
    if new_mem:
        return (f"Memory updated: new [{new_mem.id}] is active, "
                f"old [{old_memory_id}] archived as historical version (reason: {reason}).")
    return f"Supersede failed: memory [{old_memory_id}] not found."


@mcp.tool()
async def anchor_memory_search(query: str, limit: int = 4) -> str:
    """Search long-term memory using semantic + entity + emotion + recency recall.

    Parameters:
    - query: Search query or question
    - limit: Number of results to return (default: 4)
    """
    res = search_tool.search(query=query, limit=limit)
    if not res["results"]:
        return f"No memories found matching '{query}'."

    lines = [f"[Memory Search Results · {len(res['results'])} found]"]
    for r in res["results"]:
        lines.append(
            f"- [{r.get('id')}] [{r.get('category')}] {r.get('content')} "
            f"(emotion: {r.get('emotion_label')}, score: {round(r.get('score', 0.0), 2)})"
        )
        notes = lt_service.get_notes(r["id"])
        for n in notes:
            author_label = "companion" if n.get("author") in ("companion", "assistant", "daemon") else "user"
            lines.append(f"  ↳ Note ({author_label}): {n['content']}")
    return "\n".join(lines)


# ----------------- 3. Conversation Search Tool -----------------

@mcp.tool()
async def search_conversation(
    query: str,
    scope: str = "recent",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 6
) -> str:
    """Search past conversation messages by keywords/semantics and date range.

    Use this when you need to recall specific things said in earlier conversations,
    past discussions, or check chat history within a certain time window.

    Parameters:
    - query: Search keywords or sentence
    - scope: Time range: 'recent' (3 days) | '7d' (7 days) | '30d' (30 days) | '90d' (90 days) | 'all' (all history)
    - start_date: Optional start date filter in YYYY-MM-DD format
    - end_date: Optional end date filter in YYYY-MM-DD format
    - limit: Maximum number of messages to return (default: 6, max: 20)
    """
    res = conv_search_tool.search_conversation(
        query=query,
        limit=limit,
        scope=scope,
        start_date=start_date,
        end_date=end_date
    )
    if "error" in res and res["error"]:
        return f"Search conversation error: {res['error']}"

    results = res.get("results", [])
    if not results:
        return f"No conversation records found matching '{query}' in scope '{res.get('scope')}'."

    lines = [f"[Conversation Search Results · {len(results)} found (scope: {res.get('scope')})]"]
    for r in results:
        role = r.get("role", "unknown")
        dt = r.get("created_at", "")[:19]
        lines.append(f"- [{dt}] {role}: {r.get('content')}")
    return "\n".join(lines)


# ----------------- 4. Procedural Memory Tools -----------------

@mcp.tool()
async def procedural_guide_create(situation: str, playbook: str, taboos: str) -> str:
    """Create a situation-aware behavior guide (Procedural Memory).

    Records the best response strategy and absolute taboos for a specific
    recurring situation, so the companion can respond appropriately when
    that situation is detected.

    Parameters:
    - situation: Trigger situation description (e.g. 'when user is feeling anxious')
    - playbook: Best response strategy and tone guidance
    - taboos: Absolute things to avoid saying or doing in this situation
    """
    guide = guide_service.create_guide(situation=situation, playbook=playbook, taboos=taboos)
    return f"Procedural guide created [{guide.id}] for situation: '{guide.situation}'"


@mcp.tool()
async def procedural_guide_update(
    guide_id: str,
    playbook: Optional[str] = None,
    taboos: Optional[str] = None
) -> str:
    """Update an existing behavior guide's strategy or taboos.

    Parameters:
    - guide_id: Guide ID
    - playbook: Updated response strategy (optional)
    - taboos: Updated taboos list (optional)
    """
    guide = guide_service.update_guide(guide_id=guide_id, playbook=playbook, taboos=taboos)
    if guide:
        return f"Procedural guide [{guide.id}] updated (situation: {guide.situation})."
    return f"Update failed: guide [{guide_id}] not found."


if __name__ == "__main__":
    mcp.run()
