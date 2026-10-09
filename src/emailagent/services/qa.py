import logging
from datetime import datetime, timezone
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
from src.emailagent.utils.prompt import build_qa_system_instruction

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
        """Process user natural language query and return verified, grounded answer."""
        logger.info("Received mailbox Q&A query: '%s'", request.query)

        # 1. Chuyển câu hỏi của người dùng thành vector 768 chiều
        query_vector = await self.embedding_gateway.embed_text(request.query)

        # 2. Truy vấn các thread tương đồng nhất trong PostgreSQL bằng toán tử cosine <=>
        async with self.session_factory() as session:
            repo = EmailRepository(session)
            retrieved_threads = await repo.search_similar_threads(
                query_embedding=query_vector,
                account_id=request.account_id,
                top_k=settings.RAG_TOP_K,
                threshold=settings.RAG_SIMILARITY_THRESHOLD
            )

            # Lấy thông tin tài khoản mẫu để gán ngữ cảnh
            account_info = None
            if retrieved_threads:
                account_info = await repo.get_thread_account_info(retrieved_threads[0].thread_id)

            owner_email = account_info["email_address"] if account_info else settings.FALLBACK_OWNER_EMAIL
            owner_name = account_info["owner_name"] if account_info else settings.FALLBACK_OWNER_NAME
            timezone_str = account_info["timezone"] if account_info else settings.DEFAULT_TIMEZONE

        # 3. Nếu không tìm thấy bất kỳ email nào đạt ngưỡng tương đồng
        if not retrieved_threads:
            logger.info("No matching threads found above similarity threshold %.2f", settings.RAG_SIMILARITY_THRESHOLD)
            return ChatQueryResponse(
                query=request.query,
                answer="Tôi không tìm thấy thông tin hoặc email nào liên quan đến yêu cầu của bạn trong hộp thư.",
                citations=[],
                relevant_threads_count=0
            )

        # 4. Xây dựng prompt có chứa bằng chứng và gọi Gemini tổng hợp câu trả lời
        system_instruction = build_qa_system_instruction(
            reference_date=datetime.now(timezone.utc),
            owner_name=owner_name,
            owner_email=owner_email,
            retrieved_contexts=retrieved_threads,
            timezone_str=timezone_str
        )

        user_payload = [
            UntrustedPayload(
                content_id="user_question",
                text=f"Câu hỏi của người dùng: {request.query}"
            )
        ]

        logger.info("Calling LLM reasoning for Q&A with %d candidate threads...", len(retrieved_threads))
        generated_result: QAGeneratedAnswer = await self.llm.extract_structured(
            schema=QAGeneratedAnswer,
            system_instruction=system_instruction,
            untrusted_contents=user_payload
        )

        return ChatQueryResponse(
            query=request.query,
            answer=generated_result.answer,
            citations=generated_result.citations,
            relevant_threads_count=len(retrieved_threads)
        )