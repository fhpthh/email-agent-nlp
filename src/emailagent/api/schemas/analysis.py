from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field


class ThreadAnalysisData(BaseModel):
    thread_id: UUID
    status: Literal["success", "skipped", "failed"]
    source: str | None = None
    category: str | None = None
    is_urgent: bool | None = None
    needs_reply: bool | None = None
    summary: str | None = None
    action_items_count: int | None = None
    reason_code: str | None = None
    error_code: str | None = None


class BatchAnalysisData(BaseModel):
    status: Literal["success", "completed"]
    total_threads: int
    rule_filtered: int
    llm_processed: int
    total_api_calls: int
    succeeded: int
    failed: int
    details: list[ThreadAnalysisData] = Field(default_factory=list)
