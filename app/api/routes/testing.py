import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.dependencies import get_test_runner
from app.docker_runner.runner import DockerTestRunner
from app.models.test_result import TestResult

router = APIRouter(prefix="/run-tests", tags=["testing"])
logger = logging.getLogger(__name__)


class RunTestsRequest(BaseModel):
    repository_path: str


@router.post("", response_model=TestResult)
async def run_tests(
    request: RunTestsRequest,
    runner: DockerTestRunner = Depends(get_test_runner),
) -> TestResult:
    """
    Run the test suite of a repository inside Docker.
    Returns pass/fail status, test counts, and full output.
    """
    try:
        return runner.run_tests(request.repository_path)
    except Exception as e:
        logger.exception("Test run failed")
        raise HTTPException(status_code=500, detail=str(e))
