"""Post-test hook: parse results and block PR creation if tests failed."""
import logging

from app.models.test_result import TestResult

logger = logging.getLogger(__name__)


class HookValidationError(Exception):
    pass


def post_test_hook(test_result: TestResult) -> None:
    """Block the workflow from proceeding to PR if tests failed."""
    logger.info(
        "post_test_hook: passed=%s, %d passed, %d failed",
        test_result.passed,
        test_result.passed_tests,
        test_result.failed_tests,
    )

    if test_result.skipped:
        logger.info("post_test_hook: no test files found — skipping")
        return

    if not test_result.passed:
        raise HookValidationError(
            f"Tests failed ({test_result.failed_tests} failure(s)). "
            "PR creation blocked. The workflow will retry code generation."
        )

    logger.info("post_test_hook passed — all tests green")
