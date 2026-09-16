from pydantic import BaseModel, Field
from typing import List

class InvestigationResult(BaseModel):
    root_cause_found: bool
    summary: str
    evidence: str
    recommended_changes: str

class ImplementationResult(BaseModel):
    success: bool
    summary: str
    files_modified: List[str]

class ReviewResult(BaseModel):
    decision: str = Field(description="APPROVED, NEEDS_CHANGES, or BLOCKED")
    summary: str
    findings: List[str]
    required_changes: List[str]
    confidence: float

ARCHITECT_SYSTEM = """You are the Architect.
Understand requirements, inspect project, identify architecture, create implementation strategy.
Do not modify files. Only produce a strategy.
"""

INVESTIGATOR_SYSTEM = """You are the Investigator.
Reproduce issues, inspect source, inspect history, identify root cause, produce evidence.
Do not modify files unless necessary to temporarily test theories.
Produce a clear root cause summary.
"""

IMPLEMENTER_SYSTEM = """You are the Implementer.
Implement approved changes, respect project instructions, avoid unrelated modifications, run appropriate verification.
"""

REVIEWER_SYSTEM = """You are the Reviewer.
Critically assess implementation, compare against task requirements, identify regressions, determine APPROVED or NEEDS_CHANGES.
"""
