"""
Exact symbol matcher.

Extracts potential symbol names from the issue text and looks them up
directly in the symbol index by name. Fast, zero-cost, no embeddings needed.
"""
import logging
import re

from app.models.retrieval import RetrievedContext
from app.models.symbol import Symbol, SymbolIndex

logger = logging.getLogger(__name__)

# Patterns to extract identifiers from issue text
_IDENTIFIER_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")
_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _tokenize_issue(text: str) -> set[str]:
    """Extract all potential symbol names from issue text."""
    tokens: set[str] = set()
    for match in _IDENTIFIER_RE.finditer(text):
        word = match.group(1)
        tokens.add(word.lower())
        # Split camelCase: registerUser → ["register", "User"]
        parts = _CAMEL_SPLIT_RE.split(word)
        tokens.update(p.lower() for p in parts if len(p) > 2)
        # Also try snake_case join: ["register", "User"] → "register_user"
        if len(parts) > 1:
            tokens.add("_".join(p.lower() for p in parts))
        # Split snake_case: get_user_email → {get, user, email}
        tokens.update(p.lower() for p in word.split("_") if len(p) > 2)
    return tokens


class ExactMatcher:
    def __init__(self, symbol_index: SymbolIndex) -> None:
        # Build a lowercase lookup map: name → Symbol
        self._lookup: dict[str, Symbol] = {
            s.name.lower(): s for s in symbol_index.symbols
        }

    def match(self, issue_text: str) -> list[RetrievedContext]:
        """
        Find symbols whose names appear (exactly or as sub-tokens) in the issue text.
        Returns results sorted by match confidence (exact name match scores higher).
        """
        tokens = _tokenize_issue(issue_text)
        results: list[RetrievedContext] = []
        seen: set[str] = set()

        for token in tokens:
            symbol = self._lookup.get(token)
            if symbol and symbol.name not in seen:
                seen.add(symbol.name)
                # Full name match scores 1.0; sub-token match scores 0.7
                score = 1.0 if token == symbol.name.lower() else 0.7
                results.append(
                    RetrievedContext(symbol=symbol, score=score, match_type="exact")
                )

        results.sort(key=lambda r: r.score, reverse=True)
        logger.debug("Exact match found %d symbols", len(results))
        return results
