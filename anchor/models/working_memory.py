"""Working Memory Pydantic Models."""
from typing import Optional, Literal
from pydantic import BaseModel


class WorkingMemoryItem(BaseModel):
    id: str
    content: str
    category: str = "general"
    status: Literal["active", "expired"] = "active"
    created_at: str
    created_by: str = "companion"
    expired_at: Optional[str] = None
    expire_reason: Optional[str] = None
    auto_clear_after_days: int = 2


class WorkingMemoryCreate(BaseModel):
    content: str
    category: str = "general"


class WorkingMemoryUpdate(BaseModel):
    content: str


class WorkingMemoryExpire(BaseModel):
    item_id: str
    reason: str = "resolved"


class WorkingMemoryRestore(BaseModel):
    item_id: str
    restore_reason: str = "false positive recovery"
