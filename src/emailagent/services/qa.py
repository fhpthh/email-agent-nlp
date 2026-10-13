import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.emailagent.adapters.db.repositories import EmailRepository
from src.emailagent.config import settings
from src.emailagent.domain.models import (
    ChatQueryRequest,
    ChatQueryResponse,
    QAGeneratedAnswer
)
from src.emailagent.ports.embedding import EmbeddingGateway
from src.emailagent.ports.llm import LLMGateway, UntrustedPayload
from src.emailagent.prompts.qa import get_qa_static_system_instruction, build_qa_user_context_block
from src.emailagent.prompts.rewriter import build_query_rewriter_prompt
from src.emailagent.utils.security import verify_and_filter_citations

logger = logging.getLogger("emailagent.services.qa")


class MailboxQAService:

    def __init__(
            self,
            embedding_gateway: EmbeddingGateway,
            llm_gateway: LLMGateway,
            session_factory: async_sessionmaker
    ):
        self.embedding_gateway = embedding_gateway
        self.llm = llm_gateway
        self.session_factory = session_factory

    async def ask_mailbox(self, request: ChatQueryRequest) -> ChatQueryResponse:
        logger.info("Received mailbox Q&A query: '%s'", request.query)

        effective_query = request.query
        rewritten_query = None

        # 1. Multi-turn Adaptive Routing
        if request.chat_history and len(request.chat_history) > 0:
            recent_turns = request.chat_history[-4:]
            rewrite_prompt = build_query_rewriter_prompt(
                chat_history=recent_turns,
                latest_query=request.query
            )
            try:
                rewritten_text = await self.llm.generate_response(prompt=rewrite_prompt)
                rewritten_text = rewritten_text.strip().strip('"').strip("'")
                if rewritten_text:
                    effective_query = rewritten_text
                    rewritten_query = rewritten_text
                    logger.info("Query rewritten: '%s' -> '%s'", request.query, effective_query)
            except Exception as e:
                logger.warning("Rewriting failed: %s. Using original query.", e)
                effective_query = request.query

        # 2. Tự động bóc tách bộ lọc thời gian từ câu hỏi (Temporal Filter)
        date_after = None
        q_lower = request.query.lower()
        now_utc = datetime.now(timezone.utc)

        if any(w in q_lower for w in ["gần đây", "vừa rồi", "tuần này", "recently", "latest"]):
            date_after = now_utc - timedelta(days=7)
        elif any(w in q_lower for w in ["hôm nay", "đêm qua", "tối qua", "hôm qua", "yesterday", "today"]):
            date_after = now_utc - timedelta(days=2)

        # 3. Vector Embedding & Hybrid Retrieval
        query_vector = await self.embedding_gateway.embed_text(effective_query)
        top_k = request.top_k or 8  # Tăng lên 8 threads để mở rộng phễu ứng viên

        async with self.session_factory() as session:
            repo = EmailRepository(session)
            retrieved_threads = await repo.search_similar_threads(
                query_embedding=query_vector,
                query_text=effective_query,
                account_id=request.account_id,
                date_after=date_after,
                top_k=top_k,
                threshold=settings.RAG_SIMILARITY_THRESHOLD
            )

            account_info = None
            if retrieved_threads:
                account_info = await repo.get_thread_account_info(retrieved_threads[0].thread_id)

            owner_email = account_info["email_address"] if account_info else settings.FALLBACK_OWNER_EMAIL
            owner_name = account_info["owner_name"] if account_info else settings.FALLBACK_OWNER_NAME
            timezone_str = account_info["timezone"] if account_info else settings.DEFAULT_TIMEZONE

        if not retrieved_threads:
            return ChatQueryResponse(
                query=request.query,
                rewritten_query=rewritten_query,
                answer="Tôi không tìm thấy thông tin hoặc email nào liên quan đến yêu cầu của bạn trong hộp thư.",
                citations=[],
                relevant_threads_count=0
            )

        # 4. Đóng gói Context an toàn
        user_context_str, thread_raw_texts = build_qa_user_context_block(
            retrieved_contexts=retrieved_threads,
            reference_date=now_utc,
            owner_name=owner_name,
            owner_email=owner_email,
            timezone_str=timezone_str
        )

        system_instruction = get_qa_static_system_instruction()

        user_payload = [
            UntrustedPayload(
                content_id="mailbox_evidence_and_query",
                text=f"{user_context_str}\n\nCÂU HỎI CỦA NGƯỜI DÙNG: {request.query}"
            )
        ]

        # 5. Gọi LLM trích xuất câu trả lời
        generated_result: QAGeneratedAnswer = await self.llm.extract_structured(
            schema=QAGeneratedAnswer,
            system_instruction=system_instruction,
            untrusted_contents=user_payload
        )

        # 6. Gán Subject & Kiểm chứng Citation bằng code Python
        thread_subject_map = {str(t.thread_id): t.subject for t in retrieved_threads}
        for citation in generated_result.citations:
            citation.subject = thread_subject_map.get(citation.thread_id, "Không có tiêu đề")

        verified_citations = verify_and_filter_citations(
            citations=generated_result.citations,
            thread_texts=thread_raw_texts
        )

        return ChatQueryResponse(
            query=request.query,
            rewritten_query=rewritten_query,
            answer=generated_result.answer,
            citations=verified_citations,
            relevant_threads_count=len(retrieved_threads)
        )