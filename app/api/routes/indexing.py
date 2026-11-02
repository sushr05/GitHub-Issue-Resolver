import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agents.indexing_agent import RepositoryIndexingAgent
from app.api.dependencies import get_indexing_agent
from app.models.symbol import SymbolIndex

router = APIRouter(prefix="/index-repository", tags=["indexing"])
logger = logging.getLogger(__name__)


class IndexRequest(BaseModel):
    repository_path: str


class IndexResponse(BaseModel):
    repository_path: str
    total_files: int
    total_symbols: int
    indexed_at: str
    message: str


@router.post("", response_model=IndexResponse)
async def index_repository(
    request: IndexRequest,
    agent: RepositoryIndexingAgent = Depends(get_indexing_agent),
) -> IndexResponse:
    """
    Scan a local repository, parse all Python/JS/TS files with Tree-sitter,
    extract symbols, generate embeddings, and store in FAISS.

    Must be called before POST /process-issue.
    """
    try:
        index: SymbolIndex = agent.index_repository(request.repository_path)
        return IndexResponse(
            repository_path=index.repository_path,
            total_files=index.total_files,
            total_symbols=index.total_symbols,
            indexed_at=index.indexed_at,
            message=f"Successfully indexed {index.total_symbols} symbols from {index.total_files} files.",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Indexing failed")
        raise HTTPException(status_code=500, detail=str(e))
