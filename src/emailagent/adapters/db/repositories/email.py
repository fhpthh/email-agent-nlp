import logging
from typing import List
from uuid import UUID
from sqlalchemy import text

from src.emailagent.domain.models import RawEmailMessage
from .base import BaseRepository

logger = logging.getLogger("emailagent.db.repository.email")


class EmailSyncRepository(BaseRepository):
    """Repository quản lý việc ingest, lưu trữ email thô và threads."""

    async def upsert_thread(self, account_id: UUID, provider_thread_id: str, subject: str, last_message_at) -> UUID:
        """Lưu hoặc cập nhật thread."""
        query = text("""
            INSERT INTO threads (account_id, provider_thread_id, subject, last_message_at)
            VALUES (:account_id, :provider_thread_id, :subject, :last_message_at)
            ON CONFLICT (account_id, provider_thread_id) DO UPDATE
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
                    :date_sent, :subject, :clean_body, 'PENDING')
            ON CONFLICT (account_id, provider_message_id) DO UPDATE
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
            ORDER BY date_sent DESC
            LIMIT :limit;
        """)
        result = await self._session.execute(query, {"limit": limit})
        return [dict(row._mapping) for row in result.fetchall()]

    async def get_thread_emails(self, thread_id: UUID) -> List[dict]:
        """Lấy tất cả email của một thread sắp xếp theo thứ tự thời gian tăng dần."""
        query = text("""
            SELECT id, sender, recipients, subject, clean_body, date_sent, status
            FROM emails
            WHERE thread_id = :thread_id
            ORDER BY date_sent ASC;
        """)
        result = await self._session.execute(query, {"thread_id": thread_id})
        return [dict(row._mapping) for row in result.fetchall()]