import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.emailagent.adapters.db.repositories import EmailRepository
from src.emailagent.config import settings
from src.emailagent.domain.models import ThreadInsightModel
from src.emailagent.ports.llm import LLMGateway, UntrustedPayload
from src.emailagent.utils.fingerprint import compute_action_item_fingerprint
from src.emailagent.utils.prompt import build_analysis_system_instruction

logger = logging.getLogger("emailagent.services.analysis")


class ThreadAnalysisService:
    def __init__(
            self,
            llm_gateway: LLMGateway,
            session_factory: async_sessionmaker,
            concurrency_limit: int = 3
    ):
        self.llm = llm_gateway
        self.session_factory = session_factory
        self.semaphore = asyncio.Semaphore(concurrency_limit)

    async def analyze_thread(self, thread_id: UUID) -> Dict[str, Any]:
        """Phân tích một chuỗi hội thoại đơn lẻ bằng LLM."""
        async with self.semaphore:
            async with self.session_factory() as session:
                repo = EmailRepository(session)
                emails = await repo.get_thread_emails(thread_id)

                if not emails:
                    logger.warning("No emails found for thread %s", thread_id)
                    return {"thread_id": str(thread_id), "status": "skipped", "reason": "empty_thread"}

                #  Chuẩn bị payload an toàn từ các email trong thread
                payloads: List[UntrustedPayload] = []
                pending_email_ids: List[UUID] = []
                latest_date = emails[-1]["date_sent"]

                for mail in emails:
                    if mail["status"] == "PENDING":
                        pending_email_ids.append(mail["id"])

                    body_snippet = mail["clean_body"] or "(Không có nội dung)"
                    formatted_msg = (
                        f"From: {mail['sender']}\n"
                        f"Date: {mail['date_sent'].isoformat()}\n"
                        f"Subject: {mail['subject']}\n"
                        f"Content:\n{body_snippet}"
                    )
                    payloads.append(UntrustedPayload(content_id=str(mail["id"]), text=formatted_msg))

                #  Lấy thông tin chủ hộp thư thật từ DB
                account_info = await repo.get_thread_account_info(thread_id)
                owner_email = account_info["email_address"] if account_info else settings.FALLBACK_OWNER_EMAIL
                owner_name = account_info["owner_name"] if account_info else settings.FALLBACK_OWNER_NAME
                timezone_str = account_info["timezone"] if account_info else settings.DEFAULT_TIMEZONE

                # Truyền email và tên thật vào Prompt
                system_instruction = build_analysis_system_instruction(
                    reference_date=latest_date or datetime.now(timezone.utc),
                    owner_email=owner_email,
                    owner_name=owner_name,
                    timezone_str=timezone_str
                )

                # Gọi Gemini LLM với Native Structured Output
                logger.info("Analyzing thread %s (%d messages) via LLM...", thread_id, len(payloads))
                insight: ThreadInsightModel = await self.llm.extract_structured(
                    schema=ThreadInsightModel,
                    system_instruction=system_instruction,
                    untrusted_contents=payloads
                )

                #  Chuẩn bị Action Items với mã hash fingerprint
                action_items_data = []
                for item in insight.action_items:
                    fp = compute_action_item_fingerprint(task=item.task, deadline=item.deadline)
                    action_items_data.append({
                        "task": item.task,
                        "assignee": item.assignee,
                        "deadline": item.deadline,
                        "priority": item.priority.value,
                        "evidence": item.evidence,
                        "fingerprint": fp
                    })

                # Lưu vào PostgreSQL trong 1 Transaction nguyên khối (@Transactional)
                async with session.begin():
                    await repo.save_thread_insight_and_action_items(
                        thread_id=thread_id,
                        summary=insight.summary,
                        category=insight.category.value,
                        is_urgent=insight.is_urgent,
                        needs_reply=insight.needs_reply,
                        action_items=action_items_data,
                        processed_email_ids=pending_email_ids
                    )

                logger.info(
                    "Thread %s processed successfully: Category=%s, Urgent=%s, Tasks=%d",
                    thread_id, insight.category.value, insight.is_urgent, len(action_items_data)
                )

                return {
                    "thread_id": str(thread_id),
                    "status": "success",
                    "category": insight.category.value,
                    "is_urgent": insight.is_urgent,
                    "needs_reply": insight.needs_reply,
                    "summary": insight.summary,
                    "action_items_count": len(action_items_data)
                }

    async def process_pending_threads(self, limit: int = 20) -> Dict[str, Any]:
        """Quét và phân tích toàn bộ các thread đang có email PENDING."""
        async with self.session_factory() as session:
            repo = EmailRepository(session)
            threads = await repo.get_threads_with_pending_emails(limit=limit)

        if not threads:
            logger.info("No pending threads to process.")
            return {"status": "success", "processed_threads": 0, "details": []}

        logger.info("Found %d pending threads to analyze. Starting batch...", len(threads))

        # Chạy song song có kiểm soát bởi Semaphore
        tasks = [self.analyze_thread(t["id"]) for t in threads]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        succeeded = 0
        failed = 0
        details = []

        for r in results:
            if isinstance(r, Exception):
                failed += 1
                logger.error("Error analyzing thread: %s", r)
                details.append({"status": "failed", "error": str(r)})
            else:
                succeeded += 1
                details.append(r)

        return {
            "status": "completed",
            "total_threads": len(threads),
            "succeeded": succeeded,
            "failed": failed,
            "details": details
        }
