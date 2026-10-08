from datetime import date, datetime
from typing import List, Optional
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