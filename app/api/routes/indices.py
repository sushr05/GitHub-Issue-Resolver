"""
GET /indices

Returns a list of all repositories that have been indexed,
reading metadata from each symbol_index.json under data/indices/.
"""
import json
import logging
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/indices", tags=["indices"])
logger = logging.getLogger(__name__)


class IndexSummary(BaseModel):
    repo_name: str
    repository_path: str
    total_files: int
    total_symbols: int
    indexed_at: str


@router.get("", response_model=list[IndexSummary])
async def list_indices() -> list[IndexSummary]:
    """Scan data/indices/ and return metadata for every indexed repository."""
    parent_dir = Path(settings.symbol_index_path).parent
    indices_dir = parent_dir / "indices"

    if not indices_dir.exists():
        return []

    results: list[IndexSummary] = []
    for repo_dir in sorted(indices_dir.iterdir()):
        if not repo_dir.is_dir():
            continue
        symbol_file = repo_dir / "symbol_index.json"
        if not symbol_file.exists():
            continue
        try:
            data = json.loads(symbol_file.read_text())
            results.append(IndexSummary(
                repo_name=repo_dir.name,
                repository_path=data.get("repository_path", ""),
                total_files=data.get("total_files", 0),
                total_symbols=data.get("total_symbols", 0),
                indexed_at=data.get("indexed_at", ""),
            ))
        except Exception as e:
            logger.warning("Failed to read index for %s: %s", repo_dir.name, e)

    # Most recently indexed first
    results.sort(key=lambda r: r.indexed_at, reverse=True)
    return results
