import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.emailagent.adapters.db.repositories import EmailRepository
from src.emailagent.config import settings
from src.emailagent.domain.models import (
    AnalyticsGeneratedAnswer, ChatQueryRequest, ChatQueryResponse, QAGeneratedAnswer,
    QueryFormulationResult, QueryIntent,
)
from src.emailagent.ports.embedding import EmbeddingGateway
from src.emailagent.ports.llm import LLMGateway
from src.emailagent.prompts.analytics import build_analytics_prompt
from src.emailagent.prompts.contexts import RuntimeContext
from src.emailagent.prompts.loader import PROMPTS_RESOURCE_DIR
from src.emailagent.prompts.qa import build_qa_prompt
from src.emailagent.prompts.rewriter import build_query_formulation_prompt
from src.emailagent.prompts.settings import configured_budgets
from src.emailagent.utils.security import verify_and_filter_citations

logger = logging.getLogger(__name__)
_MESSAGES = json.loads((PROMPTS_RESOURCE_DIR / "qa/messages.json").read_text(encoding="utf-8"))


class MailboxQAService:
    def __init__(self, embedding_gateway: EmbeddingGateway, llm_gateway: LLMGateway,
                 session_factory: async_sessionmaker):
        self.embedding_gateway = embedding_gateway
        self.llm = llm_gateway
        self.session_factory = session_factory

    async def ask_mailbox(self, request: ChatQueryRequest) -> ChatQueryResponse:
        now = datetime.now(timezone.utc)
        account = None
        if request.account_id:
            async with self.session_factory() as session:
                account = await EmailRepository(session).get_account_info(request.account_id)
        runtime = RuntimeContext.create(
            now, (account or {}).get("timezone") or settings.DEFAULT_TIMEZONE,
            owner_name=(account or {}).get("owner_name") or settings.FALLBACK_OWNER_NAME,
            owner_email=(account or {}).get("email_address") or settings.FALLBACK_OWNER_EMAIL,
        )
        budgets = configured_budgets()
        formulation = build_query_formulation_prompt(
            request.chat_history or [], request.query, now, runtime.timezone, budgets=budgets,
        )
        plan = await self.llm.extract_structured(schema=QueryFormulationResult, prompt=formulation)
        rewritten = plan.standalone_query if plan.standalone_query != request.query else None
        category = plan.category.value if plan.category else None

        if plan.intent == QueryIntent.ANALYTICS:
            async with self.session_factory() as session:
                stats = await EmailRepository(session).get_analytics_summary(
                    account_id=request.account_id, metric=plan.analytics_metric, category=category,
                    date_after=plan.date_after, date_before=plan.date_before,
                )
            prompt = build_analytics_prompt(stats, {
                "metric": plan.analytics_metric, "category": category,
                "date_after_inclusive": plan.date_after.isoformat() if plan.date_after else None,
                "date_before_exclusive": plan.date_before.isoformat() if plan.date_before else None,
                "account_scope": "selected_account" if request.account_id else "all_configured_accounts",
            }, runtime, request.query)
            result = await self.llm.extract_structured(schema=AnalyticsGeneratedAnswer, prompt=prompt)
            return ChatQueryResponse(query=request.query, rewritten_query=rewritten, answer=result.answer)

        vector = await self.embedding_gateway.embed_text(plan.standalone_query)
        async with self.session_factory() as session:
            threads = await EmailRepository(session).search_similar_threads(
                query_embedding=vector, query_text=plan.standalone_query,
                expanded_keywords=plan.expanded_keywords, account_id=request.account_id,
                date_after=plan.date_after, date_before=plan.date_before, category=category,
                top_k=request.top_k or settings.RAG_TOP_K, threshold=settings.RAG_SIMILARITY_THRESHOLD,
            )
        if not threads:
            return ChatQueryResponse(query=request.query, rewritten_query=rewritten,
                                     answer=_MESSAGES[runtime.output_language]["no_results"])

        prompt, raw_snippets = build_qa_prompt(threads, runtime, request.query, budgets)
        result = await self.llm.extract_structured(schema=QAGeneratedAnswer, prompt=prompt)
        verified = verify_and_filter_citations(result.citations, raw_snippets)
        # Reject the whole answer rather than silently retaining claims whose quotes failed.
        # This validates source membership, not semantic entailment of every claim.
        if not result.evidence_sufficient or not verified or len(verified) != len(result.citations):
            logger.warning("QA_GROUNDING_REJECTED prompt_hash=%s supplied=%d verified=%d",
                           prompt.trace.bundle_hash, len(result.citations), len(verified))
            return ChatQueryResponse(
                query=request.query, rewritten_query=rewritten,
                answer=_MESSAGES[runtime.output_language]["insufficient_evidence"],
                relevant_threads_count=len(threads),
            )
        subjects = {str(thread.thread_id): thread.subject for thread in threads}
        for citation in verified:
            citation.subject = subjects[citation.thread_id]
        return ChatQueryResponse(
            query=request.query, rewritten_query=rewritten, answer=result.answer,
            citations=verified, relevant_threads_count=len(threads),
        )
