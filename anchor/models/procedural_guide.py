"""Procedural Guide Pydantic Models."""
from typing import Optional
from pydantic import BaseModel


class ProceduralGuide(BaseModel):
    id: str
    situation: str
    playbook: str
    taboos: str
    confidence: float = 0.8
    created_at: str
    updated_at: str


class ProceduralGuideCreate(BaseModel):
    situation: str
    playbook: str
    taboos: str
    confidence: float = 0.8


class ProceduralGuideUpdate(BaseModel):
    playbook: Optional[str] = None
    taboos: Optional[str] = None
