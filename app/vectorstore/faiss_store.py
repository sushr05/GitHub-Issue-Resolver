"""
FAISS vector store for semantic code search.

Stores embeddings of function source code. Each slot in the FAISS index
maps 1:1 to the same position in the symbols list — that list is the
bridge from a FAISS result (slot number) back to the actual Symbol object.

Embedding model: all-MiniLM-L6-v2 (free, local, 384-dim vectors)
FAISS index type: IndexFlatIP (inner product / cosine similarity)
"""
import logging
import pickle
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from app.models.retrieval import RetrievedContext
from app.models.symbol import Symbol

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 output dimension


class FAISSStore:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        logger.info("Loading embedding model: %s", model_name)
        self._model = SentenceTransformer(model_name)
        self._index: faiss.IndexFlatIP = faiss.IndexFlatIP(EMBEDDING_DIM)
        # Parallel list to FAISS slots — slot i ↔ self._symbols[i]
        self._symbols: list[Symbol] = []

    def add_symbols(self, symbols: list[Symbol]) -> None:
        """Embed source code of each symbol and add to the FAISS index."""
        if not symbols:
            return

        texts = [s.source_code for s in symbols]
        vectors = self._embed(texts)

        self._index.add(vectors)
        self._symbols.extend(symbols)

        logger.info("Added %d symbols to FAISS (total: %d)", len(symbols), len(self._symbols))

    def search(self, query: str, top_k: int = 10) -> list[RetrievedContext]:
        """Embed query and return top-k most similar symbols."""
        if self._index.ntotal == 0:
            return []

        query_vector = self._embed([query])
        k = min(top_k, self._index.ntotal)
        distances, indices = self._index.search(query_vector, k)

        results: list[RetrievedContext] = []
        for dist, slot in zip(distances[0], indices[0]):
            if slot < 0:  # FAISS returns -1 for empty slots
                continue
            symbol = self._symbols[slot]
            # Normalize distance to 0-1 score (inner product is already cosine-like after L2 norm)
            score = float(np.clip(dist, 0.0, 1.0))
            results.append(
                RetrievedContext(symbol=symbol, score=score, match_type="semantic")
            )

        return results

    def save(self, index_path: Path) -> None:
        """Persist FAISS index + symbols list to disk."""
        index_path = Path(index_path)
        index_path.parent.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self._index, str(index_path) + ".faiss")

        with open(str(index_path) + ".symbols.pkl", "wb") as f:
            pickle.dump(self._symbols, f)

        logger.info("Saved FAISS index to %s", index_path)

    def load(self, index_path: Path) -> None:
        """Load a previously saved FAISS index + symbols list."""
        index_path = Path(index_path)
        faiss_file = str(index_path) + ".faiss"
        symbols_file = str(index_path) + ".symbols.pkl"

        if not Path(faiss_file).exists():
            raise FileNotFoundError(f"FAISS index not found at {faiss_file}")

        self._index = faiss.read_index(faiss_file)

        with open(symbols_file, "rb") as f:
            self._symbols = pickle.load(f)

        logger.info(
            "Loaded FAISS index with %d vectors from %s",
            self._index.ntotal,
            index_path,
        )

    def _embed(self, texts: list[str]) -> np.ndarray:
        """Generate L2-normalized embeddings for a list of texts."""
        vectors = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        # L2-normalize so inner product == cosine similarity
        faiss.normalize_L2(vectors)
        return vectors.astype(np.float32)

    @property
    def total_symbols(self) -> int:
        return len(self._symbols)
