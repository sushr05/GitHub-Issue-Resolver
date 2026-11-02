from pydantic import BaseModel


class TestResult(BaseModel):
    passed: bool
    exit_code: int
    output: str
    duration_seconds: float
    total_tests: int = 0
    failed_tests: int = 0
    passed_tests: int = 0
    skipped: bool = False  # True when no test files found — pipeline continues to PR
