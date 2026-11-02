from enum import Enum

from pydantic import BaseModel


class SymbolType(str, Enum):
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    CLASS = "class"
    METHOD = "method"


class Symbol(BaseModel):
    name: str
    symbol_type: SymbolType
    file_path: str
    start_line: int
    end_line: int
    source_code: str
    language: str
    docstring: str | None = None


class SymbolIndex(BaseModel):
    # symbols list maintains the same order as FAISS slots
    symbols: list[Symbol]
    repository_path: str
    indexed_at: str
    total_files: int
    total_symbols: int
