from typing import List, Optional

from pydantic import BaseModel, Field


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    document_ids: Optional[List[str]] = None


class SourceEvidence(BaseModel):
    document: str
    page: Optional[int] = None
    section: Optional[str] = None
    snippet: str
    score: float


class ConflictItem(BaseModel):
    documents: List[str]
    reason: str
    values: Optional[dict] = None


class InvestigationResult(BaseModel):
    answer: str
    verdict: str
    confidence: int
    confidence_label: str
    key_findings: List[str]
    conflicts: List[ConflictItem]
    sources: List[SourceEvidence]
