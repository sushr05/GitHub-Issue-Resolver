
from typing_extensions import TypedDict

from app.models.issue import IssueAnalysis, IssueInput
from app.models.patch import PatchSet
from app.models.pr import PRDraft
from app.models.retrieval import RetrievalResult
from app.models.test_result import TestResult


class AgentState(TypedDict):
    """Shared state passed between every node in the LangGraph workflow."""
    issue: IssueInput
    analysis: IssueAnalysis | None
    retrieval: RetrievalResult | None
    patch_set: PatchSet | None
    test_result: TestResult | None
    pr_draft: PRDraft | None
    error: str | None
    retry_count: int
