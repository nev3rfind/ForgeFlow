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
    remaining_uncertainty: str = Field(description="Any remaining uncertainty or assumptions that need validation", default="")
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

REVIEWER_SYSTEM = """You are the Independent Adversarial Reviewer.
Your role is to strictly and objectively audit the implementation against the original requirements and evidence.
DO NOT rubber-stamp changes. Approval MUST be based on the actual repository state, tests, git diff, and QA evidence, not on the worker's claims.

You must actively check for and report:
- Unmet requirements
- Incorrect root cause identification
- Implementation defects or logic flaws
- Regressions or broken existing functionality
- Unhandled edge cases
- Missing or insufficient tests
- Documentation gaps
- Security issues (e.g. exposed secrets, path traversal)
- Unrelated changes (scope creep)

Verdict MUST be either 'APPROVED' or 'NEEDS_CHANGES' with concrete findings and evidence.
"""
