"""
Retrieval Agent

Responsibilities:
- Run exact symbol matching on the issue text
- Run semantic FAISS search
- Merge and deduplicate results
- Return ranked RetrievalResult
"""
import logging

from app.models.issue import IssueInput
from app.models.retrieval import RetrievalResult, RetrievedContext
from app.models.symbol import SymbolIndex
from app.retrieval.exact_matcher import ExactMatcher
from app.retrieval.semantic_retriever import SemanticRetriever
from app.vectorstore.faiss_store import FAISSStore

logger = logging.getLogger(__name__)


class RetrievalAgent:
    def __init__(self, symbol_index: SymbolIndex, faiss_store: FAISSStore) -> None:
        self._exact = ExactMatcher(symbol_index)
        self._semantic = SemanticRetriever(faiss_store)

    def retrieve(self, issue: IssueInput, top_k: int = 10) -> RetrievalResult:
        """
        Hybrid retrieval:
        1. Exact match on symbol names from issue text
        2. Semantic search via FAISS
        3. Merge: exact matches take priority, semantic fills remaining slots
        """
        query = f"{issue.title}\n{issue.description}"

        exact_results = self._exact.match(query)
        semantic_results = self._semantic.retrieve(query, top_k=top_k)

        merged = self._merge(exact_results, semantic_results, top_k=top_k)

        logger.info(
            "Retrieval: %d exact, %d semantic → %d merged",
            len(exact_results),
            len(semantic_results),
            len(merged),
        )

        return RetrievalResult(
            query=query,
            results=merged,
            total_exact=len(exact_results),
            total_semantic=len(semantic_results),
            merged_count=len(merged),
        )

    @staticmethod
    def _merge(
        exact: list[RetrievedContext],
        semantic: list[RetrievedContext],
        top_k: int,
    ) -> list[RetrievedContext]:
        """
        Merge exact and semantic results, deduplicating by symbol name.
        Exact matches always come first.
        """
        seen: set[str] = set()
        merged: list[RetrievedContext] = []

        for ctx in exact:
            key = ctx.symbol.name
            if key not in seen:
                seen.add(key)
                merged.append(ctx)

        for ctx in semantic:
            key = ctx.symbol.name
            if key not in seen:
                seen.add(key)
                merged.append(ctx)

        return merged[:top_k]
