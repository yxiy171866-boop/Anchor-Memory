"""Long-term Memory Pydantic Models."""
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    id: str
    content: str
    category: str = "general"
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal: float = Field(default=0.0, ge=0.0, le=1.0)
    emotion_label: str = "neutral"
    entities: List[str] = Field(default_factory=list)
    links: List[str] = Field(default_factory=list)
    decay_score: float = 1.0
    status: Literal["active", "superseded", "archived"] = "active"
    superseded_by: Optional[str] = None
    backfilled: int = 0
    created_at: str
    updated_at: str
    last_accessed_at: str


class MemoryCreate(BaseModel):
    content: str
    category: str = "general"
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal: float = Field(default=0.0, ge=0.0, le=1.0)
    emotion_label: str = "neutral"
    entities: List[str] = Field(default_factory=list)
    links: List[str] = Field(default_factory=list)


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    importance: Optional[float] = None
    valence: Optional[float] = None
    arousal: Optional[float] = None
    emotion_label: Optional[str] = None


class MemorySupersede(BaseModel):
    old_memory_id: str
    new_content: str
    reason: str
