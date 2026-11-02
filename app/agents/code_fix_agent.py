"""
Code Fix Agent

Responsibilities:
- Analyze retrieved code in context of the issue
- Generate concrete code fixes
- Return structured PatchSet with FilePatch objects
"""
import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.models.issue import IssueAnalysis, IssueInput
from app.models.patch import FilePatch, PatchSet
from app.models.retrieval import RetrievalResult
from app.utils.retry import llm_retry

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an expert software engineer generating code fixes.
Given a GitHub issue, its analysis, and the relevant source code, generate precise code changes.

Rules:
- Only modify code that is directly related to the bug
- Keep changes minimal and focused
- The original_code must be the EXACT text currently in the file (copy it verbatim)
- The new_code must be valid, complete replacement code

Respond ONLY with a JSON array of patch objects matching this schema:
[
  {
    "file_path": "relative/path/to/file.py",
    "operation": "replace",
    "original_code": "exact code to replace (verbatim from source)",
    "new_code": "the fixed replacement code",
    "start_line": 12,
    "end_line": 15,
    "description": "short description of what this change fixes"
  }
]

operation must be one of: "replace", "insert", "delete"
For "insert": set original_code to null, start_line is where to insert after.
For "delete": set new_code to "", original_code is the exact block to remove."""


class CodeFixAgent:
    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    @llm_retry
    def generate_fix(
        self,
        issue: IssueInput,
        analysis: IssueAnalysis,
        context: RetrievalResult,
    ) -> PatchSet:
        """Generate code patches for the issue based on analysis and retrieved code."""
        context_block = self._format_context(context)
        user_prompt = f"""## Issue
Title: {issue.title}
Description: {issue.description}

## Root Cause Analysis
{analysis.root_cause}

## Suggested Approach
{analysis.suggested_approach}

## Relevant Source Code
{context_block}

Generate the minimal code changes to fix this bug. Respond with JSON array only."""

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        logger.info("Generating code fix for: %s", issue.title)
        response = self._llm.invoke(messages)
        raw = response.content.strip()

        # Strip markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0]

        try:
            patches_data = json.loads(raw)
            if not isinstance(patches_data, list):
                patches_data = [patches_data]

            patches = [FilePatch(**p) for p in patches_data]
            unique_files = len({p.file_path for p in patches})

            patch_set = PatchSet(
                patches=patches,
                total_files=unique_files,
                description=f"Fix for: {issue.title}",
            )
            logger.info("Generated %d patches across %d files", len(patches), unique_files)
            return patch_set

        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.error("Failed to parse LLM patch response: %s\nRaw: %s", e, raw)
            raise ValueError(f"LLM returned invalid patch JSON: {e}") from e

    @staticmethod
    def _format_context(context: RetrievalResult) -> str:
        if not context.results:
            return "No relevant code found."
        parts = []
        for ctx in context.results:
            s = ctx.symbol
            parts.append(
                f"File: {s.file_path} (lines {s.start_line}-{s.end_line})\n"
                f"```{s.language}\n{s.source_code}\n```"
            )
        return "\n\n".join(parts)
