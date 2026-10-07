import logging
from typing import List, Optional
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.emailagent.domain.models import RawEmailMessage

logger = logging.getLogger("emailagent.db.repository")


class EmailRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_or_create_account(self, email_address: str, owner_name: str, provider: str = "fake") -> UUID:
        """Lấy hoặc tạo mới account_id."""
        query = text("""
                     INSERT INTO accounts (provider, email_address, owner_name)
                     VALUES (:provider, :email_address, :owner_name) ON CONFLICT (email_address) DO
                     UPDATE
                         SET owner_name = EXCLUDED.owner_name
                         RETURNING id;
                     """)
        result = await self._session.execute(query, {
            "provider": provider,
            "email_address": email_address,
            "owner_name": owner_name
        })
        return result.scalar_one()

    async def upsert_thread(self, account_id: UUID, provider_thread_id: str, subject: str, last_message_at) -> UUID:
        """Lưu hoặc cập nhật thread."""
        query = text("""
                     INSERT INTO threads (account_id, provider_thread_id, subject, last_message_at)
                     VALUES (:account_id, :provider_thread_id, :subject,
                             :last_message_at) ON CONFLICT (account_id, provider_thread_id) DO
                     UPDATE
                         SET subject = EXCLUDED.subject,
                         last_message_at = GREATEST(threads.last_message_at, EXCLUDED.last_message_at)
                         RETURNING id;
                     """)
        result = await self._session.execute(query, {
            "account_id": account_id,
            "provider_thread_id": provider_thread_id,
            "subject": subject,
            "last_message_at": last_message_at
        })
        return result.scalar_one()

    async def upsert_email(self, account_id: UUID, thread_id: UUID, email: RawEmailMessage, clean_body: str) -> None:
        """Lưu email có tính Idempotent (chống trùng lặp theo account_id và provider_message_id)."""
        query = text("""
                     INSERT INTO emails (account_id, thread_id, provider_message_id, sender, recipients,
                                         date_sent, subject, clean_body, status)
                     VALUES (:account_id, :thread_id, :provider_message_id, :sender, :recipients,
                             :date_sent, :subject, :clean_body,
                             'PENDING') ON CONFLICT (account_id, provider_message_id) DO
                     UPDATE
                         SET clean_body = EXCLUDED.clean_body,
                         subject = EXCLUDED.subject;
                     """)
        await self._session.execute(query, {
            "account_id": account_id,
            "thread_id": thread_id,
            "provider_message_id": email.provider_message_id,
            "sender": email.sender,
            "recipients": email.recipients,
            "date_sent": email.date_sent,
            "subject": email.subject,
            "clean_body": clean_body
        })

    async def list_emails(self, limit: int = 20) -> List[dict]:
        """Truy vấn danh sách email đã ingest trong CSDL."""
        query = text("""
                     SELECT id, provider_message_id, sender, subject, date_sent, status
                     FROM emails
                     ORDER BY date_sent DESC LIMIT :limit;
                     """)
        result = await self._session.execute(query, {"limit": limit})
        return [dict(row._mapping) for row in result.fetchall()]
