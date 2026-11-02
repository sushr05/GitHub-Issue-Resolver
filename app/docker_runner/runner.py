"""
Docker Test Runner

Mounts the target repository into a Python 3.11 container and runs pytest.
Captures stdout/stderr, parses pass/fail counts, returns TestResult.
"""
import logging
import re
import time
from pathlib import Path

import docker
from docker.errors import DockerException

from app.config import settings
from app.models.test_result import TestResult

logger = logging.getLogger(__name__)

# Regex to parse pytest summary line: "5 passed, 1 failed in 1.23s"
_PYTEST_SUMMARY_RE = re.compile(
    r"(?:(\d+) passed)?.*?(?:(\d+) failed)?.*?in [\d.]+s"
)


class DockerTestRunner:
    def __init__(self) -> None:
        try:
            self._client = docker.from_env()
            self._client.ping()
            logger.info("Docker daemon connected")
        except DockerException as e:
            logger.error("Docker not available: %s", e)
            self._client = None

    def run_tests(self, repository_path: str) -> TestResult:
        """
        Run pytest inside a Docker container against the repository.
        The repo folder is mounted as a volume — Docker picks up any
        file changes the patch applicator made on disk.
        """
        if not self._client:
            return TestResult(
                passed=False,
                exit_code=1,
                output="Docker daemon not available.",
                duration_seconds=0.0,
            )

        repo_path = Path(repository_path).resolve()
        if not repo_path.exists():
            return TestResult(
                passed=False,
                exit_code=1,
                output=f"Repository path not found: {repo_path}",
                duration_seconds=0.0,
            )

        # Skip Docker entirely if the repo has no test files
        test_files = list(repo_path.rglob("test_*.py")) + list(repo_path.rglob("*_test.py"))
        if not test_files:
            logger.info("No test files found in %s — skipping tests", repo_path)
            return TestResult(
                passed=True,
                exit_code=0,
                output="No test files found in repository — skipping tests.",
                duration_seconds=0.0,
                skipped=True,
            )

        logger.info("Running tests in Docker for: %s", repo_path)
        start = time.time()

        try:
            # Install deps + run pytest in one command
            # The repo is mounted at /repo inside the container
            output = self._client.containers.run(
                image="python:3.11-slim",
                command="bash -c 'pip install -q pytest && pytest -v --tb=short 2>&1'",
                volumes={str(repo_path): {"bind": "/repo", "mode": "rw"}},
                working_dir="/repo",
                remove=True,
                stdout=True,
                stderr=True,
                timeout=settings.docker_timeout,
            )
            stdout = output.decode("utf-8", errors="replace")
            exit_code = 0

        except docker.errors.ContainerError as e:
            stdout = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
            exit_code = e.exit_status
        except docker.errors.APIError as e:
            stdout = str(e)
            exit_code = 1

        duration = time.time() - start
        passed_count, failed_count = self._parse_counts(stdout)
        passed = exit_code == 0

        logger.info(
            "Tests %s in %.1fs: %d passed, %d failed",
            "PASSED" if passed else "FAILED",
            duration,
            passed_count,
            failed_count,
        )

        return TestResult(
            passed=passed,
            exit_code=exit_code,
            output=stdout,
            duration_seconds=round(duration, 2),
            total_tests=passed_count + failed_count,
            passed_tests=passed_count,
            failed_tests=failed_count,
        )

    @staticmethod
    def _parse_counts(output: str) -> tuple[int, int]:
        """Extract pass/fail counts from pytest summary line."""
        for line in reversed(output.splitlines()):
            m = _PYTEST_SUMMARY_RE.search(line)
            if m:
                passed = int(m.group(1) or 0)
                failed = int(m.group(2) or 0)
                return passed, failed
        return 0, 0
