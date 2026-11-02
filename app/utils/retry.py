"""
Shared retry utilities for LLM calls.

- Detects 429 rate-limit errors and waits much longer (up to 90s)
- Regular errors get standard exponential backoff (up to 15s)
- Adds random jitter to avoid hammering the API in sync
"""
import logging
import random

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
)

logger = logging.getLogger(__name__)


def _is_rate_limit(exc: BaseException) -> bool:
    """Return True if this exception looks like a 429 / quota error."""
    msg = str(exc).lower()
    return any(k in msg for k in ("429", "rate limit", "quota", "resource_exhausted", "too many requests"))


def _is_retryable(exc: BaseException) -> bool:
    """Retry on rate limits AND transient server errors (5xx)."""
    msg = str(exc).lower()
    return _is_rate_limit(exc) or any(k in msg for k in ("500", "502", "503", "504", "timeout"))


def _wait_for_rate_limit(retry_state) -> float:
    """
    If the error is a rate limit, wait 45-90s (matches what Gemini/HF ask for).
    Otherwise use standard exponential backoff with jitter.
    """
    exc = retry_state.outcome.exception()
    if exc and _is_rate_limit(exc):
        wait = random.uniform(45, 90)
        logger.warning("Rate limit hit — waiting %.0fs before retry", wait)
        return wait
    # Standard backoff: 2^attempt seconds + jitter, capped at 15s
    backoff = min(2 ** retry_state.attempt_number, 15)
    jitter = random.uniform(0, 3)
    return backoff + jitter


llm_retry = retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(5),
    wait=_wait_for_rate_limit,
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
