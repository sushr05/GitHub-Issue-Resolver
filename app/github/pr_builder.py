import logging

from app.github.client import get_github_client
from app.models.pr import PRDraft

logger = logging.getLogger(__name__)


class PRBuilder:
    def create_pr(self, draft: PRDraft) -> PRDraft:
        """Create a GitHub pull request. Returns draft unchanged if GitHub is unavailable."""
        client = get_github_client()
        if not client.available:
            logger.warning("GitHub not configured — skipping PR creation. Draft returned as-is.")
            return draft

        repo = client.get_repo()
        if not repo:
            logger.warning("Could not fetch GitHub repo — skipping PR creation.")
            return draft

        try:
            pr = repo.create_pull(
                title=draft.title,
                body=draft.description,
                base=draft.base_branch,
                head=draft.head_branch,
            )
            logger.info("PR created: %s", pr.html_url)
            return PRDraft(
                **draft.model_dump(exclude={"pr_url", "pr_number"}),
                pr_url=pr.html_url,
                pr_number=pr.number,
            )
        except Exception as e:
            logger.error("Failed to create PR: %s", e)
            return draft
