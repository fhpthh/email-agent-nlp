import logging
from typing import List, Optional
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.emailagent.domain.models import RawEmailMessage, RetrievedThreadContext

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

    async def get_threads_with_pending_emails(self, limit: int = 20) -> List[dict]:
        """Lấy danh sách thread đang có ít nhất 1 email ở trạng thái PENDING."""
        query = text("""
            SELECT DISTINCT t.id, t.subject, t.account_id, a.timezone
            FROM threads t
            JOIN emails e ON e.thread_id = t.id
            JOIN accounts a ON a.id = t.account_id
            WHERE e.status = 'PENDING'
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

    async def save_thread_insight_and_action_items(
        self,
        thread_id: UUID,
        summary: str,
        category: str,
        is_urgent: bool,
        needs_reply: bool,
        action_items: List[dict],
        processed_email_ids: List[UUID]
    ) -> None:
        """
        Thực thi lưu kết quả phân tích:
        1. Cập nhật bảng threads.
        2. Insert action_items (ON CONFLICT DO NOTHING dựa trên fingerprint).
        3. Cập nhật status các email thành 'PROCESSED'.
        """
        # 1. Cập nhật thread
        update_thread_query = text("""
            UPDATE threads
            SET summary = :summary,
                category = :category,
                is_urgent = :is_urgent,
                needs_reply = :needs_reply
            WHERE id = :thread_id;
        """)
        await self._session.execute(update_thread_query, {
            "thread_id": thread_id,
            "summary": summary,
            "category": category,
            "is_urgent": is_urgent,
            "needs_reply": needs_reply
        })

        # 2. Insert action items (nếu có)
        if action_items:
            insert_task_query = text("""
                INSERT INTO action_items (
                    thread_id, task, assignee, deadline, priority, evidence, fingerprint, status
                ) VALUES (
                    :thread_id, :task, :assignee, :deadline, :priority, :evidence, :fingerprint, 'open'
                ) ON CONFLICT (thread_id, fingerprint) DO NOTHING;
            """)
            for item in action_items:
                await self._session.execute(insert_task_query, {
                    "thread_id": thread_id,
                    "task": item["task"],
                    "assignee": item.get("assignee"),
                    "deadline": item.get("deadline"),
                    "priority": item.get("priority", "medium"),
                    "evidence": item["evidence"],
                    "fingerprint": item["fingerprint"]
                })

        # 3. Đánh dấu các email đã phân tích thành PROCESSED
        if processed_email_ids:
            update_emails_query = text("""
                UPDATE emails
                SET status = 'PROCESSED'
                WHERE id = ANY(:email_ids);
            """)
            await self._session.execute(update_emails_query, {
                "email_ids": processed_email_ids
            })
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

    async def get_threads_missing_embeddings(self, limit: int = 50) -> List[dict]:
        """Fetch threads that have summaries but lack vector embeddings."""
        query = text("""
            SELECT id, subject, category, summary
            FROM threads
            WHERE summary IS NOT NULL
              AND embedding IS NULL
            ORDER BY created_at DESC
            LIMIT :limit;
        """)
        result = await self._session.execute(query, {"limit": limit})
        return [dict(row._mapping) for row in result.fetchall()]

    async def update_thread_embedding(self, thread_id: UUID, embedding: List[float]) -> None:
        """Update pgvector column for a specific thread."""
        vector_str = f"[{','.join(f'{x:.6f}' for x in embedding)}]"
        # Dùng CAST(:embedding AS vector) thay cho :embedding::vector
        query = text("""
                     UPDATE threads
                     SET embedding = CAST(:embedding AS vector)
                     WHERE id = :thread_id;
                     """)
        await self._session.execute(query, {
            "thread_id": thread_id,
            "embedding": vector_str
        })

    async def search_similar_threads(
            self,
            query_embedding: List[float],
            account_id: Optional[UUID] = None,
            top_k: int = 5,
            threshold: float = 0.60
    ) -> List[RetrievedThreadContext]:
        """Perform cosine similarity search on threads using pgvector <=> operator."""
        vector_str = f"[{','.join(f'{x:.6f}' for x in query_embedding)}]"

        # 1. Khởi tạo danh sách điều kiện WHERE mặc định
        conditions = [
            "t.embedding IS NOT NULL",
            "(1 - (t.embedding <=> CAST(:query_vector AS vector))) >= :threshold"
        ]

        params: dict = {
            "query_vector": vector_str,
            "threshold": threshold,
            "top_k": top_k
        }

        # 2. Chỉ bổ sung điều kiện lọc account_id khi có giá trị truyền vào (tránh AmbiguousParameterError)
        if account_id is not None:
            conditions.append("t.account_id = :account_id")
            params["account_id"] = account_id

        where_clause = " AND ".join(conditions)

        # 3. Lắp ráp câu truy vấn SQL động
        query = text(f"""
            SELECT 
                t.id AS thread_id,
                t.subject,
                t.category,
                t.summary,
                t.last_message_at,
                (1 - (t.embedding <=> CAST(:query_vector AS vector))) AS similarity_score
            FROM threads t
            WHERE {where_clause}
            ORDER BY similarity_score DESC
            LIMIT :top_k;
        """)

        result = await self._session.execute(query, params)
        rows = result.fetchall()
        return [
            RetrievedThreadContext(
                thread_id=row.thread_id,
                subject=row.subject or "(Không có tiêu đề)",
                category=row.category or "uncategorized",
                summary=row.summary or "",
                similarity_score=float(row.similarity_score),
                last_message_at=row.last_message_at
            )
            for row in rows
        ]