"""Pre-code-generation hook: validates issue payload and retrieved context."""
import logging

from app.models.issue import IssueInput
from app.models.retrieval import RetrievalResult

logger = logging.getLogger(__name__)


class HookValidationError(Exception):
    pass


def pre_code_generation_hook(issue: IssueInput, context: RetrievalResult) -> None:
    """Raise HookValidationError if the state is not safe to proceed with code generation."""
    if not issue.title.strip():
        raise HookValidationError("Issue title is empty.")
    if not issue.description.strip():
        raise HookValidationError("Issue description is empty.")
    if not issue.repository_path:
        raise HookValidationError("repository_path is required.")
    if not context.results:
        raise HookValidationError(
            "No relevant code retrieved. Cannot generate a fix without context. "
            "Ensure the repository is indexed first via POST /index-repository."
        )
    logger.info(
        "pre_code_generation_hook passed: %d context items available", len(context.results)
    )
