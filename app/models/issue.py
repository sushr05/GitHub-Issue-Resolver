from enum import Enum

from pydantic import BaseModel, Field


class IssueSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueInput(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(..., min_length=1)
    issue_number: int | None = None
    labels: list[str] = Field(default_factory=list)
    repository_path: str = Field(default="", description="Absolute local path to the repository (set automatically after cloning)")


class IssueAnalysis(BaseModel):
    root_cause: str
    reasoning: str
    affected_files: list[str]
    suggested_approach: str
    severity: IssueSeverity
    confidence: float = Field(..., ge=0.0, le=1.0)
    keywords: list[str] = Field(default_factory=list, description="Symbol names to search for")
