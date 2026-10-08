from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from google.genai._gaos.types import basemodel
from pydantic import BaseModel, Field

from src.emailagent.domain.enums import EmailCategory, PriorityLevel


# Nhiệm vụ cụ thể cần làm trích xuất từ email
class ActionItemModel(BaseModel):
    task: str = Field(..., description="Actionable task description")
    assignee: Optional[str] = Field(None, description="Assigned owner if mentioned")
    deadline: Optional[date] = Field(None, description="Resolved deadline date")
    priority: PriorityLevel = Field(PriorityLevel.MEDIUM, description="Task urgency priority")
    evidence: str = Field(..., description="Verbatim quote from email as proof")


# Kết quả phân tích của toàn bộ chuỗi hội thoại (Thread)
class ThreadInsightModel(BaseModel):
    category: EmailCategory = Field(..., description="Classified email category")
    is_urgent: bool = Field(False, description="Requires immediate same-day attention")
    needs_reply: bool = Field(False, description="Waiting for user response")
    summary: str = Field(..., description="2-3 sentence executive summary")
    action_items: List[ActionItemModel] = Field(default_factory=list, description="Extracted action items")


# Dữ liệu email chuẩn hóa độc lập với provider
class RawEmailMessage(BaseModel):
    provider_message_id: str
    provider_thread_id: str
    sender: str
    recipients: List[str]
    subject: str
    date_sent: datetime
    body_text: str
    body_html: Optional[str] = None


# Kết quả phân tích của 1 thread trong mảng batch
class ThreadAnalysisItem(BaseModel):
    thread_id: str = Field(..., description="Thread id")
    category: EmailCategory = Field(..., description="Classified email category")
    is_urgent: bool = Field(False, description="Requires immediate same-day attention")
    needs_reply: bool = Field(False, description="Waiting for user response")
    summary: str = Field(..., description="2-3 sentence executive summary")
    action_items: List[ActionItemModel] = Field(default_factory=list, description="Extracted action items")


# DTO tổng bọc danh sách các thread gửi lên 1 lần
class BatchThreadInsightModel(BaseModel):
    threads: List[ThreadAnalysisItem] = Field(
        default_factory=list,
        description="List result analytics for thread"
    )


# ============================================================================
#  VECTOR MEMORY & CHAT Q&A MODELS
# ============================================================================

class RetrievedThreadContext(BaseModel):
    """DTO ngữ cảnh luồng thư lấy từ pgvector"""
    thread_id: UUID
    subject: str
    category: str
    summary: str
    similarity_score: float = Field(..., description="Cosine similarity score (0.0 to 1.0)")
    last_message_at: Optional[datetime] = None


class CitationItem(BaseModel):
    """Thông tin trích dẫn nguồn"""
    thread_id: str = Field(..., description="ID of the referenced thread")
    subject: str = Field(..., description="Subject of the referenced email")
    evidence: str = Field(..., description="Verbatim evidence text supporting the statement")


class QAGeneratedAnswer(BaseModel):
    """Kết quả Q&A do LLM sinh ra"""
    answer: str = Field(..., description="Detailed answer addressing user question")
    citations: List[CitationItem] = Field(default_factory=list, description="List of source citations used")


class ChatQueryRequest(BaseModel):
    """Request tìm kiếm/hỏi đáp hộp thư"""
    query: str = Field(..., min_length=2, description="Natural language question about mailbox")
    account_id: Optional[UUID] = Field(None, description="Optional account ID filter")


class ChatQueryResponse(BaseModel):
    """Response trả lời cho client"""
    query: str = Field(..., description="Original user question")
    answer: str = Field(..., description="Grounded answer synthesized by AI Agent")
    citations: List[CitationItem] = Field(default_factory=list, description="List of verified citations")
    relevant_threads_count: int = Field(0, description="Number of candidate threads inspected")


class ThreadEmbeddingSyncResult(BaseModel):
    """Kết quả đồng bộ embedding theo batch."""
    total_found: int = Field(0, description="Total threads needing embeddings")
    synced: int = Field(0, description="Successfully embedded and saved threads")
    failed: int = Field(0, description="Failed threads count")