from datetime import date, datetime
from typing import List, Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field, AwareDatetime, model_validator

from src.emailagent.domain.enums import EmailCategory, PriorityLevel, QueryIntent


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
    is_unread: bool = False


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

class EmailMessageSnippet(BaseModel):
    message_id: str
    sender: str
    date_sent: Optional[datetime] = None
    body_snippet: str


class RetrievedThreadContext(BaseModel):
    """DTO ngữ cảnh luồng thư lấy từ pgvector"""
    thread_id: UUID
    subject: str
    category: str
    summary: str
    similarity_score: float = Field(..., description="Cosine similarity score (0.0 to 1.0)")
    last_message_at: Optional[datetime] = None
    messages: List[EmailMessageSnippet] = Field(default_factory=list)


class CitationItem(BaseModel):
    """Thông tin trích dẫn nguồn"""
    thread_id: str = Field(..., description="ID of the referenced thread")
    subject: Optional[str] = Field(None, description="Subject populated from database by backend code")
    evidence: str = Field(..., description="Verbatim evidence text supporting the statement")


class AnalyticsGeneratedAnswer(BaseModel):
    answer: str


class QAGeneratedAnswer(BaseModel):
    """Kết quả Q&A do LLM sinh ra"""
    answer: str = Field(..., description="Detailed answer addressing user question")
    evidence_sufficient: bool = Field(..., description="Whether supplied snippets support the answer")
    citations: List[CitationItem] = Field(default_factory=list, description="List of source citations used")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatQueryRequest(BaseModel):
    """Request tìm kiếm/hỏi đáp hộp thư"""
    query: str = Field(..., min_length=2, description="Natural language question about mailbox")
    account_id: Optional[UUID] = Field(None, description="Optional account ID filter")
    top_k: Optional[int] = 5

    chat_history: Optional[List[ChatMessage]] = None
    session_id: Optional[str] = None


class ChatQueryResponse(BaseModel):
    """Response trả lời cho client"""
    query: str = Field(..., description="Original user question")
    rewritten_query: Optional[str] = Field(None, description="Rewritten user question")
    answer: str = Field(..., description="Grounded answer synthesized by AI Agent")
    citations: List[CitationItem] = Field(default_factory=list, description="List of verified citations")
    relevant_threads_count: int = Field(0, description="Number of candidate threads inspected")


class ThreadEmbeddingSyncResult(BaseModel):
    """Kết quả đồng bộ embedding theo batch."""
    total_found: int = Field(0, description="Total threads needing embeddings")
    synced: int = Field(0, description="Successfully embedded and saved threads")
    failed: int = Field(0, description="Failed threads count")


class QueryFormulationResult(BaseModel):
    intent: QueryIntent = Field(default=QueryIntent.SEARCH, description="Intent")
    standalone_query: str = Field(..., description="Standalone query")
    expanded_keywords: List[str] = Field(default_factory=list, description="Expanded keyword")
    date_after: Optional[AwareDatetime] = Field(None, description="Inclusive start of the requested period")
    date_before: Optional[AwareDatetime] = Field(None, description="Exclusive end of the requested period")
    category: Optional[EmailCategory] = Field(None, description="Requested category filter")
    analytics_metric: Optional[Literal["count_threads", "count_tasks"]] = None

    @model_validator(mode="after")
    def validate_plan(self):
        if self.date_after and self.date_before and self.date_after >= self.date_before:
            raise ValueError("Date range must have a positive duration")
        if self.intent == QueryIntent.ANALYTICS and self.analytics_metric is None:
            raise ValueError("Analytics requests require a metric")
        if self.intent == QueryIntent.SEARCH and self.analytics_metric is not None:
            raise ValueError("Search requests must not specify an analytics metric")
        return self
