import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.emailagent.adapters.db.repositories import EmailRepository
from src.emailagent.config import settings
from src.emailagent.domain.models import BatchThreadInsightModel, ThreadAnalysisItem
from src.emailagent.ports.llm import LLMGateway, UntrustedPayload
from src.emailagent.utils.fingerprint import compute_action_item_fingerprint
from src.emailagent.utils.prefilter import EmailRuleEngine, default_rule_engine
from src.emailagent.utils.prompt import (
    build_analysis_system_instruction,
    format_thread_messages_to_xml
)

logger = logging.getLogger("emailagent.services.analysis")


class ThreadAnalysisService:
    def __init__(
            self,
            llm_gateway: LLMGateway,
            session_factory: async_sessionmaker,
            rule_engine: Optional[EmailRuleEngine] = None,
            concurrency_limit: int = 2
    ):
        self.llm = llm_gateway
        self.session_factory = session_factory
        self.rule_engine = rule_engine or default_rule_engine
        self.semaphore = asyncio.Semaphore(concurrency_limit)

    async def _save_thread_result(
            self,
            repo: EmailRepository,
            item: ThreadAnalysisItem,
            emails: List[Dict[str, Any]],
            source: str = "llm"
    ) -> Dict[str, Any]:
        """Lưu kết quả phân tích và action items của thread vào Database."""
        tid = UUID(item.thread_id)
        pending_ids = [m["id"] for m in emails if m.get("status") == "PENDING"]

        action_items_data = [
            {
                "task": act.task,
                "assignee": act.assignee,
                "deadline": act.deadline,
                "priority": act.priority.value,
                "evidence": act.evidence,
                "fingerprint": compute_action_item_fingerprint(act.task, act.deadline)
            }
            for act in item.action_items
        ]

        await repo.save_thread_insight_and_action_items(
            thread_id=tid,
            summary=item.summary,
            category=item.category.value,
            is_urgent=item.is_urgent,
            needs_reply=item.needs_reply,
            action_items=action_items_data,
            processed_email_ids=pending_ids
        )

        return {
            "thread_id": item.thread_id,
            "status": "success",
            "source": source,
            "category": item.category.value,
            "is_urgent": item.is_urgent,
            "needs_reply": item.needs_reply,
            "summary": item.summary,
            "action_items_count": len(action_items_data)
        }

    async def _process_single_batch(
            self,
            thread_ids: List[UUID],
            owner_email: str,
            owner_name: str,
            timezone_str: str
    ) -> List[Dict[str, Any]]:
        """Gom nhóm nhiều thread phức tạp để gọi LLM 1 lần duy nhất."""
        async with self.session_factory() as session:
            repo = EmailRepository(session)
            thread_xmls = []
            emails_by_thread = {}
            reference_date = datetime.now(timezone.utc)

            for tid in thread_ids:
                emails = await repo.get_thread_emails(tid)
                if not emails:
                    continue
                emails_by_thread[str(tid)] = emails
                reference_date = emails[-1]["date_sent"] or reference_date
                thread_xmls.append(format_thread_messages_to_xml(tid, emails))

            if not thread_xmls:
                return []

            system_instruction = build_analysis_system_instruction(
                reference_date=reference_date,
                owner_email=owner_email,
                owner_name=owner_name,
                timezone_str=timezone_str
            )
            payload = [UntrustedPayload(content_id="batch_chunk", text="\n\n".join(thread_xmls))]

            logger.info("Calling Gemini for batch of %d threads...", len(thread_xmls))
            batch_result: BatchThreadInsightModel = await self.llm.extract_structured(
                schema=BatchThreadInsightModel,
                system_instruction=system_instruction,
                untrusted_contents=payload
            )

            batch_summary = []
            for item in batch_result.threads:
                emails = emails_by_thread.get(item.thread_id, [])
                res = await self._save_thread_result(repo, item, emails, source="llm")
                batch_summary.append(res)

            await session.commit()
            return batch_summary

    async def analyze_thread(self, thread_id: UUID) -> Dict[str, Any]:
        """Phân tích một thread đơn lẻ: Ưu tiên Rule Engine (0 token), nếu không khớp mới gọi Gemini."""
        async with self.session_factory() as session:
            repo = EmailRepository(session)
            emails = await repo.get_thread_emails(thread_id)
            if not emails:
                return {"thread_id": str(thread_id), "status": "skipped", "reason": "No emails found"}

            # Fast Path
            rule_item = self.rule_engine.evaluate(thread_id, emails)
            if rule_item:
                result = await self._save_thread_result(repo, rule_item, emails, source="rule_filtered")
                await session.commit()
                return result

            account_info = await repo.get_thread_account_info(thread_id)
            owner_email = account_info["email_address"] if account_info else settings.FALLBACK_OWNER_EMAIL
            owner_name = account_info["owner_name"] if account_info else settings.FALLBACK_OWNER_NAME
            timezone_str = account_info["timezone"] if account_info else settings.DEFAULT_TIMEZONE

        # Slow Path
        results = await self._process_single_batch([thread_id], owner_email, owner_name, timezone_str)
        return results[0] if results else {"thread_id": str(thread_id), "status": "skipped"}

    async def process_pending_threads(self, limit: int = 20, batch_size: int = 5) -> Dict[str, Any]:
        """Quét và xử lý: Fast-path (Rule) -> Cognitive Path (Gom batch gọi Gemini)."""
        all_details = []
        complex_thread_ids: List[UUID] = []
        rule_count = 0
        succeeded = 0
        failed = 0

        async with self.session_factory() as session:
            repo = EmailRepository(session)
            threads = await repo.get_threads_with_pending_emails(limit=limit)
            if not threads:
                return {
                    "status": "success",
                    "total_threads": 0,
                    "rule_filtered": 0,
                    "llm_processed": 0,
                    "total_api_calls": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "details": []
                }

            account_info = await repo.get_thread_account_info(threads[0]["id"])
            owner_email = account_info["email_address"] if account_info else settings.FALLBACK_OWNER_EMAIL
            owner_name = account_info["owner_name"] if account_info else settings.FALLBACK_OWNER_NAME
            timezone_str = account_info["timezone"] if account_info else settings.DEFAULT_TIMEZONE

            # BƯỚC 1: Phân loại Fast Path (Rule Engine)
            for thread in threads:
                tid = thread["id"]
                emails = await repo.get_thread_emails(tid)
                if not emails:
                    continue

                rule_item = self.rule_engine.evaluate(tid, emails)
                if rule_item:
                    res = await self._save_thread_result(repo, rule_item, emails, source="rule_filtered")
                    all_details.append(res)
                    rule_count += 1
                    succeeded += 1
                else:
                    complex_thread_ids.append(tid)

            if rule_count > 0:
                await session.commit()

        # BƯỚC 2: Phân tích Cognitive Path (Gemini Batch)
        total_api_calls = 0
        if complex_thread_ids:
            chunks = [complex_thread_ids[i:i + batch_size] for i in range(0, len(complex_thread_ids), batch_size)]
            for chunk in chunks:
                try:
                    results = await self._process_single_batch(chunk, owner_email, owner_name, timezone_str)
                    all_details.extend(results)
                    succeeded += len(results)
                    total_api_calls += 1
                    await asyncio.sleep(1)
                except Exception as exc:
                    failed += len(chunk)
                    logger.error("Failed to process batch %s: %s", chunk, exc)
                    for tid in chunk:
                        all_details.append({"thread_id": str(tid), "status": "failed", "error": str(exc)})

        return {
            "status": "completed",
            "total_threads": len(threads),
            "rule_filtered": rule_count,
            "llm_processed": len(complex_thread_ids),
            "total_api_calls": total_api_calls,
            "succeeded": succeeded,
            "failed": failed,
            "details": all_details
        }
