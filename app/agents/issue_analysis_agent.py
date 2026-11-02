"""
Issue Analysis Agent

Responsibilities:
- Understand the GitHub issue
- Determine affected areas
- Generate an investigation plan
- Return structured IssueAnalysis
"""
import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.models.issue import IssueAnalysis, IssueInput, IssueSeverity
from app.models.retrieval import RetrievalResult
from app.utils.retry import llm_retry

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an expert software engineer analyzing a GitHub issue.
Given an issue and retrieved relevant code snippets, identify:
1. The root cause of the bug
2. Your reasoning
3. Which files are affected
4. The best approach to fix it
5. Severity level (low/medium/high/critical)
6. Confidence score (0.0 to 1.0)
7. Keywords — function/class names likely involved

Respond ONLY with valid JSON matching this exact schema:
{
  "root_cause": "string",
  "reasoning": "string",
  "affected_files": ["string"],
  "suggested_approach": "string",
  "severity": "low|medium|high|critical",
  "confidence": 0.0,
  "keywords": ["string"]
}"""


class IssueAnalysisAgent:
    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    @llm_retry
    def analyze(self, issue: IssueInput, context: RetrievalResult) -> IssueAnalysis:
        """Send issue + retrieved code to LLM, return structured analysis."""
        context_block = self._format_context(context)
        user_prompt = f"""## Issue Title
{issue.title}

## Issue Description
{issue.description}

## Retrieved Code Context
{context_block}

Analyze the issue and respond with JSON only."""

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        logger.info("Sending issue to LLM for analysis: %s", issue.title)
        response = self._llm.invoke(messages)
        raw = response.content.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            data = json.loads(raw)
            return IssueAnalysis(
                root_cause=data["root_cause"],
                reasoning=data["reasoning"],
                affected_files=data.get("affected_files", []),
                suggested_approach=data["suggested_approach"],
                severity=IssueSeverity(data.get("severity", "medium")),
                confidence=float(data.get("confidence", 0.5)),
                keywords=data.get("keywords", []),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error("Failed to parse LLM analysis response: %s\nRaw: %s", e, raw)
            raise ValueError(f"LLM returned invalid analysis JSON: {e}") from e

    @staticmethod
    def _format_context(context: RetrievalResult) -> str:
        if not context.results:
            return "No relevant code found."
        parts = []
        for i, ctx in enumerate(context.results, 1):
            s = ctx.symbol
            parts.append(
                f"[{i}] {s.name} ({s.symbol_type}) — {s.file_path}:{s.start_line}-{s.end_line}\n"
                f"Match: {ctx.match_type} (score={ctx.score:.2f})\n"
                f"```{s.language}\n{s.source_code}\n```"
            )
        return "\n\n".join(parts)
