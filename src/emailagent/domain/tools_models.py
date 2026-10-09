from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


# 1. Models cho Tool Tìm kiếm Email (Semantic Search)
class SearchMailboxToolInput(BaseModel):
    query: str = Field(..., description="Q&A and keyword for email")
    top_k: int = Field(5, description="Quality email return", ge=1, le=10)


class SearchMailboxItem(BaseModel):
    thread_id: str
    subject: str
    category: str
    summary: str
    similarity_score: float


# 2. Models cho Tool Tra cứu Nhiệm vụ & Deadline
class GetActionItemsToolInput(BaseModel):
    priority: Optional[str] = Field(None, description="Filter priority: 'high', 'medium', hoặc 'low'")
    due_before: Optional[str] = Field(None, description="Filter deadline due before (định dạng YYYY-MM-DD)")
    status: str = Field("open", description="status ('open' hoặc 'done')")


class ActionItemResult(BaseModel):
    task_id: str
    task: str
    assignee: Optional[str]
    deadline: Optional[date]
    priority: str
    evidence: str
    thread_subject: str


# 3. Models cho Tool Tra cứu Email Khẩn cấp
class GetUrgentThreadsToolInput(BaseModel):
    needs_reply_only: bool = Field(False, description="only email required reply")
    limit: int = Field(10, description="Quality email return", ge=1, le=10)


class UrgentThreadResult(BaseModel):
    thread_id: str
    subject: str
    category: str
    summary: str
    is_urgent: bool
    needs_reply: bool


# 4. Models cho Tool Đọc Chi tiết Thread
class GetThreadDetailToolInput(BaseModel):
    thread_id: str = Field(..., description="UUID thread email must return")


class EmailMessageDetail(BaseModel):
    message_id: str
    sender: str
    date_sent: str
    subject: str
    clean_body: str


# 5. Models cho Tool Lấy Danh sách Email Mới nhất / Chưa đọc
class RecentEmailItem(BaseModel):
    message_id: str
    thread_id: str
    date_sent: str
    sender: str
    subject: str
    is_unread: bool
    snippet: str

