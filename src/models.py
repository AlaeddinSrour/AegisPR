"""Pydantic models for structured LLM review output."""

from typing import List
from pydantic import BaseModel, Field


class ReviewIssue(BaseModel):
    """A single security issue identified during code review."""

    file: str = Field(
        description="The relative path to the file containing the issue."
    )
    line: int = Field(
        description=(
            "The line number (1-indexed) in the file where the issue is. "
            "MUST be a valid line number in the current version of the file."
        )
    )
    severity: str = Field(
        description="Vulnerability severity. Allowed values: CRITICAL, HIGH, WARNING, INFO."
    )
    issue_name: str = Field(
        description=(
            "Short name of the issue, e.g. SQL Injection, "
            "Vulnerable Package Import / Deprecated Dependency Semantics."
        )
    )
    description: str = Field(
        description="Strictly 1-2 sentences explaining the bug and remediation."
    )
    original_code: str = Field(
        description=(
            "Strictly the 1-2 exact lines of code that need to be replaced. "
            "Do not include entire functions. Must match exactly."
        )
    )
    suggested_fix: str = Field(
        description=(
            "Strictly the 1-2 corrected lines to replace original_code. "
            "Do not include entire functions."
        )
    )


class ReviewReport(BaseModel):
    """Complete structured review report returned by the LLM."""

    analysis_scratchpad: str = Field(
        description=(
            "Step-by-step analysis of the diff. Trace logic flow and "
            "strictly hunt for TOCTOU and SSRF before populating issues."
        )
    )
    issues: List[ReviewIssue]
