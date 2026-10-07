import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from src.emailagent.domain.models import RawEmailMessage
from src.emailagent.ports.provider import EmailProvider, SyncCursor

logger = logging.getLogger("emailagent.providers.fake")

class FakeEmailProvider(EmailProvider):
    # Constructor Injection: nhận đường dẫn file mock
    def __init__(self, mock_file_path: Path):
        self._mock_file_path = mock_file_path
        self._cached_emails: List[RawEmailMessage] = []
        self._load_mock_data()

    @property
    def provider_name(self) -> str:
        return "fake"

    def _load_mock_data(self) -> None:
        """Đọc và parse file JSON thành danh sách RawEmailMessage."""
        if not self._mock_file_path.exists():
            logger.error("Mock data file not found at: %s", self._mock_file_path)
            return

        with open(self._mock_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self._cached_emails = [RawEmailMessage(**item) for item in data]
        logger.info("Loaded %d mock emails successfully.", len(self._cached_emails))

    async def fetch_history(
        self,
        since: datetime,
        until: datetime,
        page_token: Optional[str] = None
    ) -> Tuple[List[RawEmailMessage], Optional[str]]:
        """Lọc email theo khoảng thời gian."""
        filtered = [
            e for e in self._cached_emails
            if since <= e.date_sent <= until
        ]
        return filtered, None

    async def fetch_new_changes(
        self,
        cursor: SyncCursor
    ) -> Tuple[List[RawEmailMessage], SyncCursor]:
        """Giả lập lấy email mới (với mock data trả về rỗng)."""
        new_cursor = SyncCursor(
            account_id=cursor.account_id,
            cursor_value=str(datetime.now(timezone.utc).timestamp()),
            updated_at=datetime.now(timezone.utc)
        )
        return [], new_cursor