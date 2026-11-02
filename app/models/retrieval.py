from typing import Literal

from pydantic import BaseModel, Field

from app.models.symbol import Symbol


class RetrievedContext(BaseModel):
    symbol: Symbol
    score: float = Field(..., ge=0.0, le=1.0)
    match_type: Literal["exact", "semantic"]


class RetrievalResult(BaseModel):
    query: str
    results: list[RetrievedContext]
    total_exact: int
    total_semantic: int
    merged_count: int
