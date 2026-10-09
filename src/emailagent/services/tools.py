import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.emailagent.adapters.db.repositories import EmailRepository
from src.emailagent.config import settings
from src.emailagent.domain.tools_models import (
    SearchMailboxItem,
    ActionItemResult,
    UrgentThreadResult,
    EmailMessageDetail,
    RecentEmailItem
)
from src.emailagent.ports.embedding import EmbeddingGateway

logger = logging.getLogger("emailagent.services.tools")


class MailboxToolsService:

    def __init__(
            self,
            embedding_gateway: EmbeddingGateway,
            session_factory: async_sessionmaker
    ):
        self.embedding_gateway = embedding_gateway
        self.session_factory = session_factory

    async def search_mailbox(self, query: str, top_k: int = 5) -> List[SearchMailboxItem]:
        """Tool 1: Tìm kiếm email theo ngữ nghĩa câu hỏi bằng pgvector."""
        logger.info("Tool called: search_mailbox with query='%s'", query)
        query_vector = await self.embedding_gateway.embed_text(query)

        async with self.session_factory() as session:
            repo = EmailRepository(session)
            threads = await repo.search_similar_threads(
                query_embedding=query_vector,
                top_k=top_k,
                threshold=settings.RAG_SIMILARITY_THRESHOLD
            )

        return [
            SearchMailboxItem(
                thread_id=str(t.thread_id),
                subject=t.subject,
                category=t.category,
                summary=t.summary,
                similarity_score=t.similarity_score
            )
            for t in threads
        ]

    async def get_action_items(
            self,
            priority: Optional[str] = None,
            due_before: Optional[str] = None,
            status: str = "open"
    ) -> List[ActionItemResult]:
        """Tool 2: Tra cứu danh sách công việc cần làm, deadline và người thực hiện."""
        logger.info("Tool called: get_action_items (priority=%s, due_before=%s)", priority, due_before)
        async with self.session_factory() as session:
            repo = EmailRepository(session)
            items = await repo.get_action_items(
                status=status,
                priority=priority,
                due_before=due_before
            )

        return [
            ActionItemResult(
                task_id=str(item["id"]),
                task=item["task"],
                assignee=item["assignee"],
                deadline=item["deadline"],
                priority=item["priority"],
                evidence=item["evidence"],
                thread_subject=item["thread_subject"]
            )
            for item in items
        ]

    async def get_urgent_threads(self, needs_reply_only: bool = False, limit: int = 10) -> List[UrgentThreadResult]:
        """Tool 3: Tra cứu các email khẩn cấp hoặc cần người dùng trả lời gấp."""
        logger.info("Tool called: get_urgent_threads (needs_reply_only=%s)", needs_reply_only)
        async with self.session_factory() as session:
            repo = EmailRepository(session)
            threads = await repo.get_urgent_threads(
                needs_reply_only=needs_reply_only,
                limit=limit
            )

        return [
            UrgentThreadResult(
                thread_id=str(t["id"]),
                subject=t["subject"],
                category=t["category"],
                summary=t["summary"],
                is_urgent=t["is_urgent"],
                needs_reply=t["needs_reply"]
            )
            for t in threads
        ]

    async def get_thread_detail(self, thread_id: str) -> List[EmailMessageDetail]:
        """Tool 4: Đọc chi tiết từng email nguyên văn trong một chuỗi thư."""
        logger.info("Tool called: get_thread_detail for thread_id=%s", thread_id)
        async with self.session_factory() as session:
            repo = EmailRepository(session)
            emails = await repo.get_thread_emails(UUID(thread_id))

        return [
            EmailMessageDetail(
                message_id=str(e["id"]),
                sender=e["sender"],
                date_sent=e["date_sent"].isoformat() if e.get("date_sent") else "",
                subject=e["subject"],
                clean_body=e["clean_body"][:1500]
            )
            for e in emails
        ]

    async def sync_latest_emails(self, days_back: int = 1) -> str:
        """Tool 5: Đồng bộ các email mới nhất từ Gmail API, tự động lọc phân tích NLP và cập nhật vector CSDL."""
        logger.info("Tool called: sync_latest_emails (days_back=%d)", days_back)
        try:
            from src.emailagent.adapters.provider.factory import get_configured_email_provider
            from src.emailagent.adapters.llm.factory import get_configured_llm_gateway
            from src.emailagent.services.ingestion import IngestionService
            from src.emailagent.services.analysis import ThreadAnalysisService
            from src.emailagent.services.embedding import ThreadEmbeddingService

            # 1. Kéo email mới từ Gmail
            provider = get_configured_email_provider()
            ingest_service = IngestionService(provider=provider, session_factory=self.session_factory)
            ingest_res = await ingest_service.sync_history(days_back=days_back)
            ingested_count = ingest_res.get("ingested_count", 0)

            # 2. Phân tích NLP (Rule Engine + Gemini)
            llm = get_configured_llm_gateway()
            analysis_service = ThreadAnalysisService(llm_gateway=llm, session_factory=self.session_factory)
            analysis_res = await analysis_service.process_pending_threads(limit=15, batch_size=5)

            # 3. Đồng bộ pgvector embeddings
            embed_service = ThreadEmbeddingService(embedding_gateway=self.embedding_gateway, session_factory=self.session_factory)
            embed_res = await embed_service.sync_pending_embeddings(limit=15, batch_size=5)

            rule_count = analysis_res.get("rule_filtered", 0)
            llm_count = analysis_res.get("llm_processed", 0)

            return (
                f"Đã hoàn thành đồng bộ hộp thư trong {days_back} ngày gần nhất:\n"
                f"- Tìm thấy và lưu {ingested_count} email mới vào cơ sở dữ liệu.\n"
                f"- Đã xử lý phân loại: {rule_count} email lọc tự động, {llm_count} chuỗi email phân tích chuyên sâu.\n"
                f"- Đã cập nhật vector ngữ nghĩa cho {embed_res.synced} chuỗi email.\n"
                f"Hộp thư của bạn hiện đã được cập nhật trạng thái mới nhất!"
            )
        except Exception as exc:
            logger.error("Failed to sync and refresh mailbox: %s", exc)
            return f"Quá trình đồng bộ email mới gặp lỗi: {str(exc)}. Vui lòng kiểm tra lại kết nối mạng hoặc token Gmail."

    async def get_recent_emails(
        self,
        days_back: int = 1,
        unread_only: bool = False,
        limit: int = 10
    ) -> List[RecentEmailItem]:
        """Tool 6: Lấy danh sách email gần đây trực tiếp từ Gmail kèm trạng thái đọc/chưa đọc và thời gian."""
        logger.info("Tool called: get_recent_emails (days_back=%d, unread_only=%s, limit=%d)", days_back, unread_only, limit)
        from datetime import datetime, timedelta, timezone
        from src.emailagent.adapters.provider.factory import get_configured_email_provider

        provider = get_configured_email_provider()
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days_back)

        raw_emails, _ = await provider.fetch_history(since=since, until=now)
        raw_emails.sort(key=lambda x: x.date_sent, reverse=True)

        if unread_only:
            raw_emails = [e for e in raw_emails if e.is_unread]

        raw_emails = raw_emails[:limit]

        results = []
        for e in raw_emails:
            # Quy đổi sang múi giờ Việt Nam (UTC+7) khớp chuẩn với giao diện Gmail
            vn_tz = timezone(timedelta(hours=7))
            local_dt = e.date_sent.astimezone(vn_tz) if e.date_sent.tzinfo else e.date_sent
            date_display = local_dt.strftime("%H:%M ngày %d/%m/%Y")
            snippet = e.body_text[:140].replace("\n", " ").strip() if e.body_text else ""
            results.append(
                RecentEmailItem(
                    message_id=e.provider_message_id,
                    thread_id=e.provider_thread_id,
                    date_sent=date_display,
                    sender=e.sender,
                    subject=e.subject or "(Không có tiêu đề)",
                    is_unread=e.is_unread,
                    snippet=snippet
                )
            )
        return results


