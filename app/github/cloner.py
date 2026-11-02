"""
Repo cloner — clones a GitHub URL to a local workspace directory.

If the repo is already cloned, pulls latest instead of re-cloning.
"""
import logging
import re
import shutil
from pathlib import Path

import git

from app.config import settings

logger = logging.getLogger(__name__)


def _repo_name_from_url(url: str) -> str:
    """Extract owner/repo slug from a GitHub URL for use as folder name."""
    # handles https://github.com/owner/repo and https://github.com/owner/repo.git
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if match:
        return match.group(1).replace("/", "_")
    raise ValueError(f"Cannot parse GitHub URL: {url}")


class RepoCloner:
    def clone_or_pull(self, github_url: str) -> str:
        """
        Clone the repo if not already present, otherwise git pull.
        Returns the absolute local path to the cloned repo.
        """
        workspace = Path(settings.workspace_dir)
        workspace.mkdir(parents=True, exist_ok=True)

        repo_name = _repo_name_from_url(github_url)
        repo_path = workspace / repo_name

        if repo_path.exists():
            logger.info("Removing existing clone at %s — re-cloning fresh", repo_path)
            shutil.rmtree(repo_path)

        logger.info("Cloning %s → %s", github_url, repo_path)
        git.Repo.clone_from(github_url, repo_path)

        logger.info("Repo ready at %s", repo_path)
        return str(repo_path)
