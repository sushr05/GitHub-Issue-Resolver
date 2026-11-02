"""
PR Generation Agent

Responsibilities:
- Generate PR title and description via LLM
- Summarize files changed and root cause
- Create the GitHub pull request via PyGithub
- Return PRDraft with pr_url populated
"""
import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.github.pr_builder import PRBuilder
from app.models.issue import IssueAnalysis, IssueInput
from app.models.patch import PatchSet
from app.models.pr import PRDraft
from app.models.test_result import TestResult
from app.utils.retry import llm_retry

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a senior software engineer writing a pull request description.
Given an issue, its analysis, and the changes made, generate a clear PR.

Respond ONLY with JSON:
{
  "title": "fix: concise description (max 72 chars)",
  "description": "Markdown PR body with ## Summary, ## Root Cause, ## Changes sections",
  "root_cause_summary": "one sentence root cause",
  "file_summaries": {"path/to/file.py": "what changed in this file"}
}"""


class PRGenerationAgent:
    def __init__(self, llm: BaseChatModel, pr_builder: PRBuilder | None = None) -> None:
        self._llm = llm
        self._pr_builder = pr_builder or PRBuilder()

    @llm_retry
    def generate_pr(
        self,
        issue: IssueInput,
        analysis: IssueAnalysis,
        patch_set: PatchSet,
        test_result: TestResult,
    ) -> PRDraft:
        """Generate PR content and create it on GitHub."""
        user_prompt = f"""## Issue
{issue.title}

## Root Cause
{analysis.root_cause}

## Approach
{analysis.suggested_approach}

## Files Changed
{chr(10).join(f"- {p.file_path}: {p.description}" for p in patch_set.patches)}

## Test Results
{"PASSED" if test_result.passed else "FAILED"} — {test_result.passed_tests} passed, {test_result.failed_tests} failed

Generate the PR title and description as JSON."""

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self._llm.invoke(messages)
        raw = response.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0]

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid PR JSON: {e}") from e

        files_changed = list({p.file_path for p in patch_set.patches})
        test_summary = (
            f"✅ {test_result.passed_tests} tests passed"
            if test_result.passed
            else f"❌ {test_result.failed_tests} tests failed"
        )

        draft = PRDraft(
            title=data["title"],
            description=data["description"],
            root_cause_summary=data["root_cause_summary"],
            files_changed=files_changed,
            file_summaries=data.get("file_summaries", {}),
            head_branch=patch_set.branch_name or "fix/auto",
            test_results_summary=test_summary,
        )

        # Create actual PR on GitHub (no-op if GitHub token not configured)
        return self._pr_builder.create_pr(draft)
