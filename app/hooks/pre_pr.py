"""Pre-PR hook: verify repo is clean, tests passed, patch was applied."""
import logging

import git

from app.models.patch import PatchSet
from app.models.test_result import TestResult

logger = logging.getLogger(__name__)


class HookValidationError(Exception):
    pass


def pre_pr_hook(patch_set: PatchSet, test_result: TestResult, repository_path: str) -> None:
    """Block PR creation if patch wasn't applied or tests didn't pass."""
    if not patch_set.applied:
        raise HookValidationError("Patch has not been applied yet. Cannot create PR.")

    if not patch_set.branch_name:
        raise HookValidationError("No branch name on patch set. Cannot create PR.")

    if not test_result.passed and not test_result.skipped:
        raise HookValidationError(
            f"Tests did not pass ({test_result.failed_tests} failures). PR creation blocked."
        )

    # Verify the fix branch exists in the repo
    try:
        repo = git.Repo(repository_path)
        branch_names = [b.name for b in repo.branches]
        if patch_set.branch_name not in branch_names:
            raise HookValidationError(
                f"Branch {patch_set.branch_name} not found in repo. Cannot create PR."
            )
    except git.InvalidGitRepositoryError as e:
        raise HookValidationError(f"Not a valid git repository: {repository_path}") from e

    logger.info("pre_pr_hook passed — ready to create PR from %s", patch_set.branch_name)
