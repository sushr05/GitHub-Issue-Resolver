from enum import Enum

from pydantic import BaseModel


class PatchOperation(str, Enum):
    REPLACE = "replace"
    INSERT = "insert"
    DELETE = "delete"


class FilePatch(BaseModel):
    file_path: str
    operation: PatchOperation
    original_code: str | None = None  # None for INSERT operations
    new_code: str
    start_line: int
    end_line: int
    description: str


class PatchSet(BaseModel):
    patches: list[FilePatch]
    total_files: int
    description: str
    applied: bool = False
    applied_at: str | None = None
    branch_name: str | None = None
