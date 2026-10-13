import logging
from typing import List, Optional
from uuid import UUID
from sqlalchemy import text

from .base import BaseRepository

logger = logging.getLogger("emailagent.db.repository.analysis")


class AnalysisRepository(BaseRepository):
    """Repository quản lý trạng thái phân tích NLP, Insights và Action Items."""

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

    async def get_action_items(
        self,
        account_id: Optional[UUID] = None,
        status: str = "open",
        priority: Optional[str] = None,
        due_before: Optional[str] = None,
        limit: int = 20
    ) -> List[dict]:
        """Truy vấn danh sách công việc (action items) đã được NLP trích xuất."""
        conditions = ["a.status = :status"]
        params: dict = {"status": status, "limit": limit}
        if account_id:
            conditions.append("t.account_id = :account_id")
            params["account_id"] = account_id
        if priority:
            conditions.append("a.priority = :priority")
            params["priority"] = priority
        if due_before:
            conditions.append("a.deadline <= :due_before")
            params["due_before"] = due_before
        where_clause = " AND ".join(conditions)
        query = text(f"""
            SELECT 
                a.id,
                a.task,
                a.assignee,
                a.deadline,
                a.priority,
                a.evidence,
                a.status,
                t.id AS thread_id,
                t.subject AS thread_subject
            FROM action_items a
            JOIN threads t ON t.id = a.thread_id
            WHERE {where_clause}
            ORDER BY a.deadline ASC NULLS LAST, a.created_at DESC
            LIMIT :limit;
        """)
        result = await self._session.execute(query, params)
        return [dict(row._mapping) for row in result.fetchall()]

    async def get_urgent_threads(
        self,
        account_id: Optional[UUID] = None,
        needs_reply_only: bool = False,
        limit: int = 10
    ) -> List[dict]:
        """Truy vấn các chuỗi email khẩn cấp hoặc cần người dùng trả lời."""
        conditions = ["(t.is_urgent = TRUE OR t.needs_reply = TRUE)"]
        params: dict = {"limit": limit}
        if account_id:
            conditions.append("t.account_id = :account_id")
            params["account_id"] = account_id
        if needs_reply_only:
            conditions.append("t.needs_reply = TRUE")
        where_clause = " AND ".join(conditions)
        query = text(f"""
            SELECT 
                t.id,
                t.subject,
                t.category,
                t.summary,
                t.is_urgent,
                t.needs_reply,
                t.last_message_at
            FROM threads t
            WHERE {where_clause}
            ORDER BY t.last_message_at DESC
            LIMIT :limit;
        """)
        result = await self._session.execute(query, params)
        return [dict(row._mapping) for row in result.fetchall()]