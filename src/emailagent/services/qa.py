import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.emailagent.adapters.db.repositories import EmailRepository
from src.emailagent.config import settings
from src.emailagent.domain.models import (
    ChatQueryRequest,
    ChatQueryResponse,
    QAGeneratedAnswer,
    QueryFormulationResult,
    QueryIntent
)
from src.emailagent.ports.embedding import EmbeddingGateway
from src.emailagent.ports.llm import LLMGateway, UntrustedPayload
from src.emailagent.prompts.qa import get_qa_static_system_instruction, build_qa_user_context_block
from src.emailagent.prompts.rewriter import build_query_formulation_prompt
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
        now_utc = datetime.now(timezone.utc)

        # 1. BƯỚC 1: SELF-QUERYING & INTENT ROUTING (Bóc tách metadata & Intent bằng LLM)
        formulation_prompt = build_query_formulation_prompt(
            chat_history=request.chat_history or [],
            latest_query=request.query,
            reference_date=now_utc
        )
        query_plan: QueryFormulationResult = await self.llm.extract_structured(
            schema=QueryFormulationResult,
            system_instruction="You are an expert Query Formulation engine. Return JSON matching schema.",
            untrusted_contents=[UntrustedPayload(content_id="query", text=formulation_prompt)]
        )

        effective_query = query_plan.standalone_query
        # Khởi tạo rewritten_query (fix lỗi báo đỏ)
        rewritten_query = effective_query if effective_query != request.query else None

        # 2. BƯỚC 2: RẼ NHÁNH DỰA TRÊN INTENT

        # --- NHÁNH A: CÂU HỎI THỐNG KÊ (ANALYTICS) ---
        if query_plan.intent == QueryIntent.ANALYTICS:
            async with self.session_factory() as session:
                repo = EmailRepository(session)
                stats = await repo.get_analytics_summary(
                    account_id=request.account_id,
                    metric=query_plan.analytics_metric,
                    category=query_plan.category,
                    date_after=query_plan.date_after,
                    date_before=query_plan.date_before
                )

            # Gửi con số thực tế từ DB cho LLM tổng hợp câu trả lời tự nhiên
            analytics_prompt = (
                f"Số liệu thực tế từ Database: {stats}.\n"
                f"Hãy trả lời câu hỏi của người dùng: '{request.query}' một cách tự nhiên, chính xác bằng tiếng Việt."
            )
            final_answer = await self.llm.generate_response(prompt=analytics_prompt)

            return ChatQueryResponse(
                query=request.query,
                rewritten_query=rewritten_query,
                answer=final_answer,
                citations=[],
                relevant_threads_count=0
            )

        # --- NHÁNH B: CÂU HỎI TRA CỨU NGỮ NGHĨA (SEARCH) ---
        query_vector = await self.embedding_gateway.embed_text(effective_query)
        top_k = request.top_k or 8

        async with self.session_factory() as session:
            repo = EmailRepository(session)
            retrieved_threads = await repo.search_similar_threads(
                query_embedding=query_vector,
                query_text=effective_query,
                expanded_keywords=query_plan.expanded_keywords,  # Từ khóa đồng nghĩa FTS
                account_id=request.account_id,
                date_after=query_plan.date_after,  # Mốc thời gian bắt đầu
                date_before=query_plan.date_before,  # Mốc thời gian kết thúc
                category=query_plan.category,
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

        # 3. Đóng gói Context an toàn
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

        # 4. Gọi LLM trích xuất câu trả lời
        generated_result: QAGeneratedAnswer = await self.llm.extract_structured(
            schema=QAGeneratedAnswer,
            system_instruction=system_instruction,
            untrusted_contents=user_payload
        )

        # 5. Gán Subject & Kiểm chứng Citation
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
