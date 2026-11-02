"""
Semantic retriever using FAISS.

Embeds the issue text and searches for the most semantically similar
function source codes in the FAISS index.
"""
import logging

from app.models.retrieval import RetrievedContext
from app.vectorstore.faiss_store import FAISSStore

logger = logging.getLogger(__name__)


class SemanticRetriever:
    def __init__(self, faiss_store: FAISSStore) -> None:
        self._store = faiss_store

    def retrieve(self, query: str, top_k: int = 10) -> list[RetrievedContext]:
        """Embed query and return top-k most similar symbols from FAISS."""
        results = self._store.search(query, top_k=top_k)
        logger.debug("Semantic retrieval returned %d results", len(results))
        return results
