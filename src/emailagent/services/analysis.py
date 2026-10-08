import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.emailagent.adapters.db.repositories import EmailRepository
from src.emailagent.config import settings
from src.emailagent.domain.models import BatchThreadInsightModel
from src.emailagent.ports.llm import LLMGateway, UntrustedPayload
from src.emailagent.utils.fingerprint import compute_action_item_fingerprint
from src.emailagent.utils.prompt import build_analysis_system_instruction

logger = logging.getLogger("emailagent.services.analysis")


class ThreadAnalysisService:
    def __init__(
            self,
            llm_gateway: LLMGateway,
            session_factory: async_sessionmaker,
            concurrency_limit: int = 2
    ):
        self.llm = llm_gateway
        self.session_factory = session_factory
        self.semaphore = asyncio.Semaphore(concurrency_limit)

    async def _process_single_batch(
            self,
            thread_ids: List[UUID],
            owner_email: str,
            owner_name: str,
            timezone_str: str
    ) -> List[Dict[str, Any]]:
        """Xử lý 1 mảng gồm nhiều thread (tối đa 5 threads) trong DUY NHẤT 1 lần gọi Gemini."""
        async with self.session_factory() as session:
            repo = EmailRepository(session)

            # 1. Thu thập emails của tất cả threads trong batch
            thread_payloads_xml = []
            threads_pending_map = {}
            reference_date = datetime.now(timezone.utc)

            for tid in thread_ids:
                emails = await repo.get_thread_emails(tid)
                if not emails:
                    continue

                pending_ids = [m["id"] for m in emails if m["status"] == "PENDING"]
                threads_pending_map[str(tid)] = pending_ids
                reference_date = emails[-1]["date_sent"] or reference_date

                # Đóng gói từng message vào trong thẻ <thread>
                messages_xml = []
                for mail in emails:
                    body = mail["clean_body"] or "(Không có nội dung)"
                    messages_xml.append(
                        f'    <untrusted_message id="{mail["id"]}">\n'
                        f'        From: {mail["sender"]}\n'
                        f'        Date: {mail["date_sent"].isoformat()}\n'
                        f'        Subject: {mail["subject"]}\n'
                        f'        Content: {body}\n'
                        f'    </untrusted_message>'
                    )
                all_msgs_str = "\n".join(messages_xml)
                thread_payloads_xml.append(f'<thread id="{str(tid)}">\n{all_msgs_str}\n</thread>')

            if not thread_payloads_xml:
                return []

            # 2. Xây dựng prompt và gọi Gemini 1 LẦN DUY NHẤT
            system_instruction = build_analysis_system_instruction(
                reference_date=reference_date,
                owner_email=owner_email,
                owner_name=owner_name,
                timezone_str=timezone_str
            )
            combined_content = "\n\n".join(thread_payloads_xml)
            payload = [UntrustedPayload(content_id="batch_chunk", text=combined_content)]

            logger.info("Calling Gemini for batch of %d threads...", len(thread_payloads_xml))
            batch_result: BatchThreadInsightModel = await self.llm.extract_structured(
                schema=BatchThreadInsightModel,
                system_instruction=system_instruction,
                untrusted_contents=payload
            )

            # 3. Lưu kết quả của từng thread trong batch vào PostgreSQL
            batch_summary = []
            for item in batch_result.threads:
                tid_str = item.thread_id
                tid_uuid = UUID(tid_str)
                pending_ids = threads_pending_map.get(tid_str, [])

                action_items_data = []
                for act in item.action_items:
                    fp = compute_action_item_fingerprint(task=act.task, deadline=act.deadline)
                    action_items_data.append({
                        "task": act.task,
                        "assignee": act.assignee,
                        "deadline": act.deadline,
                        "priority": act.priority.value,
                        "evidence": act.evidence,
                        "fingerprint": fp
                    })

                await repo.save_thread_insight_and_action_items(
                    thread_id=tid_uuid,
                    summary=item.summary,
                    category=item.category.value,
                    is_urgent=item.is_urgent,
                    needs_reply=item.needs_reply,
                    action_items=action_items_data,
                    processed_email_ids=pending_ids
                )

                batch_summary.append({
                    "thread_id": tid_str,
                    "status": "success",
                    "category": item.category.value,
                    "is_urgent": item.is_urgent,
                    "needs_reply": item.needs_reply,
                    "summary": item.summary,
                    "action_items_count": len(action_items_data)
                })

            await session.commit()
            return batch_summary


    async def analyze_thread(self, thread_id: UUID) -> Dict[str, Any]:
        """Phân tích một chuỗi hội thoại đơn lẻ bằng cách gọi batch 1 thread."""
        async with self.session_factory() as session:
            repo = EmailRepository(session)
            account_info = await repo.get_thread_account_info(thread_id)
            owner_email = account_info["email_address"] if account_info else settings.FALLBACK_OWNER_EMAIL
            owner_name = account_info["owner_name"] if account_info else settings.FALLBACK_OWNER_NAME
            timezone_str = account_info["timezone"] if account_info else settings.DEFAULT_TIMEZONE

        results = await self._process_single_batch(
            thread_ids=[thread_id],
            owner_email=owner_email,
            owner_name=owner_name,
            timezone_str=timezone_str
        )
        return results[0] if results else {"thread_id": str(thread_id), "status": "skipped"}

    async def process_pending_threads(self, limit: int = 15, batch_size: int = 5) -> Dict[str, Any]:
        """Quét và gom nhóm các thread thành từng cụm batch 5 threads để phân tích nhanh và tiết kiệm quota."""
        async with self.session_factory() as session:
            repo = EmailRepository(session)
            threads = await repo.get_threads_with_pending_emails(limit=limit)

        if not threads:
            logger.info("No pending threads to process.")
            return {"status": "success", "processed_threads": 0, "details": []}

        # Lấy thông tin tài khoản của thread đầu tiên làm mốc
        account_info = await repo.get_thread_account_info(threads[0]["id"])
        owner_email = account_info["email_address"] if account_info else settings.FALLBACK_OWNER_EMAIL
        owner_name = account_info["owner_name"] if account_info else settings.FALLBACK_OWNER_NAME
        timezone_str = account_info["timezone"] if account_info else settings.DEFAULT_TIMEZONE

        thread_ids = [t["id"] for t in threads]
        # Chia nhỏ danh sách thread thành các cụm batch_size (mỗi cụm 5 thread)
        chunks = [thread_ids[i:i + batch_size] for i in range(0, len(thread_ids), batch_size)]
        logger.info(
            "Processing %d threads split into %d batch chunks (batch_size=%d)...",
            len(threads), len(chunks), batch_size
        )

        all_details = []
        succeeded = 0
        failed = 0

        for chunk in chunks:
            try:
                results = await self._process_single_batch(
                    thread_ids=chunk,
                    owner_email=owner_email,
                    owner_name=owner_name,
                    timezone_str=timezone_str
                )
                all_details.extend(results)
                succeeded += len(results)
                await asyncio.sleep(1)
            except Exception as exc:
                failed += len(chunk)
                logger.error("Failed to process batch chunk %s: %s", chunk, exc)
                for tid in chunk:
                    all_details.append({"thread_id": str(tid), "status": "failed", "error": str(exc)})

        return {
            "status": "completed",
            "total_threads": len(threads),
            "total_api_calls": len(chunks),
            "succeeded": succeeded,
            "failed": failed,
            "details": all_details
        }
