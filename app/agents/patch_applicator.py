"""
Patch Applicator

Applies FilePatch objects to the target repository:
1. Creates a new git branch from main
2. Applies each patch to the file on disk
3. Commits the changes
"""
import logging
from datetime import UTC, datetime
from pathlib import Path

import git

from app.models.patch import FilePatch, PatchOperation, PatchSet

logger = logging.getLogger(__name__)


class PatchApplicator:
    def apply(self, patch_set: PatchSet, repository_path: str) -> PatchSet:
        """
        Apply all patches to the repository on a new branch.
        Returns updated PatchSet with applied=True and branch_name set.
        """
        repo_path = Path(repository_path)
        repo = git.Repo(repo_path)

        # Create fix branch from current HEAD (usually main)
        branch_name = self._create_branch(repo, patch_set)

        # Apply each patch
        for patch in patch_set.patches:
            self._apply_single_patch(patch, repo_path)

        # Commit all changes
        repo.git.add(A=True)
        repo.git.commit(
            "-m",
            f"fix: {patch_set.description}\n\nApplied {len(patch_set.patches)} patch(es) across {patch_set.total_files} file(s).",
        )

        logger.info("Patches applied and committed on branch: %s", branch_name)

        return PatchSet(
            patches=patch_set.patches,
            total_files=patch_set.total_files,
            description=patch_set.description,
            applied=True,
            applied_at=datetime.now(UTC).isoformat(),
            branch_name=branch_name,
        )

    def _create_branch(self, repo: git.Repo, patch_set: PatchSet) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        branch_name = f"fix/auto-{timestamp}"

        repo.git.checkout("-b", branch_name)
        logger.info("Created branch: %s", branch_name)
        return branch_name

    def _apply_single_patch(self, patch: FilePatch, repo_path: Path) -> None:
        file_path = repo_path / patch.file_path
        if not file_path.exists():
            raise FileNotFoundError(f"File not found for patching: {file_path}")

        content = file_path.read_text(encoding="utf-8")

        if patch.operation == PatchOperation.REPLACE:
            if patch.original_code and patch.original_code not in content:
                raise ValueError(
                    f"original_code not found in {patch.file_path}. "
                    "The LLM may have hallucinated the original code."
                )
            new_content = content.replace(patch.original_code, patch.new_code, 1)

        elif patch.operation == PatchOperation.INSERT:
            lines = content.splitlines(keepends=True)
            insert_at = min(patch.start_line, len(lines))
            lines.insert(insert_at, patch.new_code + "\n")
            new_content = "".join(lines)

        elif patch.operation == PatchOperation.DELETE:
            if patch.original_code:
                new_content = content.replace(patch.original_code, "", 1)
            else:
                lines = content.splitlines(keepends=True)
                del lines[patch.start_line - 1 : patch.end_line]
                new_content = "".join(lines)
        else:
            raise ValueError(f"Unknown patch operation: {patch.operation}")

        file_path.write_text(new_content, encoding="utf-8")
        logger.info("Patched: %s (%s)", patch.file_path, patch.operation)
