
from pydantic import BaseModel


class PRDraft(BaseModel):
    title: str
    description: str
    root_cause_summary: str
    files_changed: list[str]
    file_summaries: dict[str, str]
    base_branch: str = "main"
    head_branch: str
    test_results_summary: str
    pr_url: str | None = None
    pr_number: int | None = None
