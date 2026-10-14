import logging
from typing import Optional
from uuid import UUID
from sqlalchemy import text

from .base import BaseRepository

logger = logging.getLogger("emailagent.db.repository.account")


class AccountRepository(BaseRepository):
    """Repository quản lý tài khoản người dùng và chủ hộp thư."""

    async def get_or_create_account(self, email_address: str, owner_name: str, provider: str = "fake") -> UUID:
        """Lấy hoặc tạo mới account_id."""
        query = text("""
            INSERT INTO accounts (provider, email_address, owner_name)
            VALUES (:provider, :email_address, :owner_name)
            ON CONFLICT (email_address) DO UPDATE
                SET owner_name = EXCLUDED.owner_name
            RETURNING id;
        """)
        result = await self._session.execute(query, {
            "provider": provider,
            "email_address": email_address,
            "owner_name": owner_name
        })
        return result.scalar_one()

    async def get_thread_account_info(self, thread_id: UUID) -> Optional[dict]:
        """Lấy thông tin chủ hộp thư thật (email, tên, timezone) của một thread."""
        query = text("""
            SELECT a.email_address, a.owner_name, a.timezone
            FROM threads t
            JOIN accounts a ON a.id = t.account_id
            WHERE t.id = :thread_id;
        """)
        result = await self._session.execute(query, {"thread_id": thread_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None