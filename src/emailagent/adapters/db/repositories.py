import logging
from typing import List, Optional, Dict
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.emailagent.config import settings
from src.emailagent.domain.models import RawEmailMessage, RetrievedThreadContext, EmailMessageSnippet

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

    async def _fetch_thread_messages_snippets(
        self,
        thread_ids: List[UUID],
        max_per_thread: int = 3
    ) -> Dict[UUID, List[EmailMessageSnippet]]:

        if not thread_ids:
            return {}

        query = text("""
            WITH RankedEmails AS (
                SELECT 
                    e.id AS message_id,
                    e.thread_id,
                    e.sender,
                    e.date_sent,
                    SUBSTRING(COALESCE(e.clean_body, '') FROM 1 FOR 800) AS body_snippet,
                    ROW_NUMBER() OVER(PARTITION BY e.thread_id ORDER BY e.date_sent DESC) as rank_idx
                FROM emails e
                WHERE e.thread_id = ANY(:thread_ids)
            )
            SELECT message_id, thread_id, sender, date_sent, body_snippet
            FROM RankedEmails
            WHERE rank_idx <= :max_per_thread
            ORDER BY thread_id, date_sent ASC;
        """)

        result = await self._session.execute(query, {
            "thread_ids": thread_ids,
            "max_per_thread": max_per_thread
        })
        rows = result.fetchall()

        mapping: Dict[UUID, List[EmailMessageSnippet]] = {tid: [] for tid in thread_ids}
        for row in rows:
            mapping[row.thread_id].append(
                EmailMessageSnippet(
                    message_id=str(row.message_id),
                    sender=row.sender,
                    date_sent=row.date_sent,
                    body_snippet=row.body_snippet or ""
                )
            )
        return mapping

    async def search_similar_threads(
        self,
        query_embedding: List[float],
        query_text: Optional[str] = None,
        account_id: Optional[UUID] = None,
        top_k: int = 5,
        threshold: float = 0.60
    ) -> List[RetrievedThreadContext]:
        vector_str = f"[{','.join(f'{x:.6f}' for x in query_embedding)}]"
        clean_text_query = (query_text or "").strip()

        vector_query = text("""
            SELECT 
                t.id AS thread_id,
                t.subject,
                t.category,
                t.summary,
                t.last_message_at,
                (1 - (t.embedding <=> CAST(:query_vector AS vector))) AS similarity_score
            FROM threads t
            WHERE t.embedding IS NOT NULL
              AND (:account_id IS NULL OR t.account_id = :account_id)
            ORDER BY similarity_score DESC
            LIMIT :vector_limit;
        """)

        vector_res = await self._session.execute(vector_query, {
            "query_vector": vector_str,
            "account_id": account_id,
            "vector_limit": top_k * 2
        })
        vector_rows = vector_res.fetchall()

        fts_rows = []
        if clean_text_query:
            fts_query = text("""
                SELECT 
                    e.thread_id,
                    t.subject,
                    t.category,
                    t.summary,
                    t.last_message_at,
                    ts_rank_cd(e.tsv, plainto_tsquery('simple', immutable_unaccent(:text_query))) AS fts_score
                FROM emails e
                JOIN threads t ON e.thread_id = t.id
                WHERE e.tsv @@ plainto_tsquery('simple', immutable_unaccent(:text_query))
                  AND (:account_id IS NULL OR t.account_id = :account_id)
                ORDER BY fts_score DESC
                LIMIT :fts_limit;
            """)
            fts_res = await self._session.execute(fts_query, {
                "text_query": clean_text_query,
                "account_id": account_id,
                "fts_limit": top_k * 2
            })
            fts_rows = fts_res.fetchall()

        rrf_scores: Dict[UUID, float] = {}
        candidate_meta: Dict[UUID, dict] = {}

        for rank_idx, row in enumerate(vector_rows):
            tid = row.thread_id
            score = float(row.similarity_score)
            rrf_scores[tid] = rrf_scores.get(tid, 0.0) + (1.0 / (60 + rank_idx + 1))
            if tid not in candidate_meta:
                candidate_meta[tid] = {
                    "subject": row.subject,
                    "category": row.category,
                    "summary": row.summary,
                    "last_message_at": row.last_message_at,
                    "cosine_score": score
                }

        for rank_idx, row in enumerate(fts_rows):
            tid = row.thread_id
            rrf_scores[tid] = rrf_scores.get(tid, 0.0) + (1.0 / (60 + rank_idx + 1))
            if tid not in candidate_meta:
                candidate_meta[tid] = {
                    "subject": row.subject,
                    "category": row.category,
                    "summary": row.summary,
                    "last_message_at": row.last_message_at,
                    "cosine_score": 0.50  # Điểm cosine ước lượng cho match FTS
                }

        sorted_threads = sorted(rrf_scores.keys(), key=lambda t: rrf_scores[t], reverse=True)

        final_selected_ids: List[UUID] = []
        for tid in sorted_threads:
            cosine_score = candidate_meta[tid]["cosine_score"]
            if cosine_score >= threshold or tid in [r.thread_id for r in fts_rows]:
                final_selected_ids.append(tid)
            elif len(final_selected_ids) == 0 and cosine_score >= getattr(settings, "RAG_MIN_FALLBACK_THRESHOLD", 0.40):
                final_selected_ids.append(tid)

            if len(final_selected_ids) >= top_k:
                break

        if not final_selected_ids:
            return []

        max_snippets = getattr(settings, "RAG_MAX_MESSAGES_PER_THREAD", 3)
        messages_mapping = await self._fetch_thread_messages_snippets(final_selected_ids, max_per_thread=max_snippets)

        contexts = []
        for tid in final_selected_ids:
            meta = candidate_meta[tid]
            contexts.append(
                RetrievedThreadContext(
                    thread_id=tid,
                    subject=meta["subject"] or "(No title)",
                    category=meta["category"] or "uncategorized",
                    summary=meta["summary"] or "",
                    similarity_score=meta["cosine_score"],
                    last_message_at=meta["last_message_at"],
                    messages=messages_mapping.get(tid, [])
                )
            )
        return contexts

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