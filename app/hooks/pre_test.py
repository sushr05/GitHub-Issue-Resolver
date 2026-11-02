"""Pre-test hook: verify Docker is running and the repository is ready."""
import logging
from pathlib import Path

import docker
from docker.errors import DockerException

logger = logging.getLogger(__name__)


class HookValidationError(Exception):
    pass


def pre_test_hook(repository_path: str) -> None:
    """Verify Docker daemon is reachable and the repo path exists.
    Skips Docker check if the repo has no test files."""
    repo_path = Path(repository_path)
    if not repo_path.exists():
        raise HookValidationError(f"Repository path does not exist: {repository_path}")

    # If no test files exist, Docker is not needed — skip the check
    test_files = list(repo_path.rglob("test_*.py")) + list(repo_path.rglob("*_test.py"))
    if not test_files:
        logger.info("pre_test_hook: no test files found — skipping Docker check")
        return

    try:
        client = docker.from_env()
        client.ping()
        logger.info("pre_test_hook: Docker daemon is running")
    except DockerException as e:
        raise HookValidationError(
            f"Docker daemon is not running or not accessible: {e}. "
            "Start Docker Desktop and retry."
        ) from e

    logger.info("pre_test_hook passed for: %s", repository_path)
