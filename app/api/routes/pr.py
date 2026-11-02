import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.pr_generation_agent import PRGenerationAgent
from app.llm import get_llm
from app.models.issue import IssueAnalysis, IssueInput, IssueSeverity
from app.models.patch import FilePatch, PatchOperation, PatchSet
from app.models.pr import PRDraft
from app.models.test_result import TestResult

router = APIRouter(prefix="/generate-pr", tags=["pr"])
logger = logging.getLogger(__name__)


class GeneratePRRequest(BaseModel):
    repository_path: str
    issue_title: str
    issue_description: str
    root_cause: str
    suggested_approach: str
    files_changed: list[str]
    patch_description: str
    branch_name: str
    tests_passed: bool
    passed_tests: int = 0
    failed_tests: int = 0


@router.post("", response_model=PRDraft)
async def generate_pr(request: GeneratePRRequest) -> PRDraft:
    """
    Standalone PR generation — takes an already-applied patch and test results,
    generates a PR title/description via LLM, and creates the GitHub PR.
    """
    try:
        issue = IssueInput(
            title=request.issue_title,
            description=request.issue_description,
            repository_path=request.repository_path,
        )
        analysis = IssueAnalysis(
            root_cause=request.root_cause,
            reasoning="Provided via API",
            affected_files=request.files_changed,
            suggested_approach=request.suggested_approach,
            severity=IssueSeverity.MEDIUM,
            confidence=1.0,
        )
        patch_set = PatchSet(
            patches=[
                FilePatch(
                    file_path=f,
                    operation=PatchOperation.REPLACE,
                    original_code=None,
                    new_code="",
                    start_line=0,
                    end_line=0,
                    description=request.patch_description,
                )
                for f in request.files_changed
            ],
            total_files=len(request.files_changed),
            description=request.patch_description,
            applied=True,
            branch_name=request.branch_name,
        )
        test_result = TestResult(
            passed=request.tests_passed,
            exit_code=0 if request.tests_passed else 1,
            output="",
            duration_seconds=0.0,
            passed_tests=request.passed_tests,
            failed_tests=request.failed_tests,
        )

        agent = PRGenerationAgent(get_llm())
        return agent.generate_pr(issue, analysis, patch_set, test_result)

    except Exception as e:
        logger.exception("PR generation failed")
        raise HTTPException(status_code=500, detail=str(e))
