from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field
from src.emailagent.domain.models import RawEmailMessage


# Con trỏ trừu tượng lưu mốc đồng bộ (historyId với Gmail, deltaLink với Graph)
class SyncCursor(BaseModel):
    account_id: str
    cursor_value: str = Field(..., description="Provider checkpoint token")
    updated_at: datetime


# Cổng giao tiếp bắt buộc mọi adapter email phải tuân theo
class EmailProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Tên định danh của provider (ví dụ: fake, gmail)."""
        pass

    @abstractmethod
    async def fetch_history(
        self,
        since: datetime,
        until: datetime,
        page_token: Optional[str] = None
    ) -> Tuple[List[RawEmailMessage], Optional[str]]:
        """Lấy danh sách email cũ theo khoảng thời gian có phân trang."""
        pass

    @abstractmethod
    async def fetch_new_changes(
        self,
        cursor: SyncCursor
    ) -> Tuple[List[RawEmailMessage], SyncCursor]:
        """Lấy các email phát sinh mới dựa trên con trỏ cursor."""
        pass

    @abstractmethod
    def get_profile(self) -> Tuple[str, str]:
        """Lấy thông tin chủ hộp thư (email_address, owner_name)."""
        pass