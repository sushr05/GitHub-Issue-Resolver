"""Post-code-generation hook: lint, format, and validate generated patches."""
import ast
import logging
import subprocess
from pathlib import Path

from app.models.patch import PatchSet

logger = logging.getLogger(__name__)


class HookValidationError(Exception):
    pass


def post_code_generation_hook(patch_set: PatchSet, repository_path: str) -> None:
    """
    Validate the generated PatchSet:
    1. Ensure at least one patch exists
    2. Validate Python syntax of new_code for .py files
    3. Run ruff + black on affected Python files (if they exist on disk already)
    """
    if not patch_set.patches:
        raise HookValidationError("PatchSet is empty — no changes were generated.")

    repo_path = Path(repository_path)

    for patch in patch_set.patches:
        # Syntax check for Python new_code
        if patch.file_path.endswith(".py") and patch.new_code.strip():
            try:
                ast.parse(patch.new_code)
            except SyntaxError as e:
                raise HookValidationError(
                    f"Syntax error in generated patch for {patch.file_path}: {e}"
                ) from e

    # Run ruff + black on Python files that already exist in the repo
    py_files = [
        str(repo_path / p.file_path)
        for p in patch_set.patches
        if p.file_path.endswith(".py") and (repo_path / p.file_path).exists()
    ]

    if py_files:
        _run_ruff(py_files)
        _run_black(py_files)

    logger.info("post_code_generation_hook passed for %d patches", len(patch_set.patches))


def _run_ruff(files: list[str]) -> None:
    result = subprocess.run(
        ["ruff", "check", "--fix"] + files,
        capture_output=True, text=True
    )
    if result.returncode not in (0, 1):  # 1 = fixed issues
        logger.warning("ruff returned warnings: %s", result.stdout)


def _run_black(files: list[str]) -> None:
    result = subprocess.run(
        ["black"] + files,
        capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.warning("black formatting issue: %s", result.stderr)
