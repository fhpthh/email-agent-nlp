from fastapi import APIRouter, Depends

from src.emailagent.adapters.embedding.factory import get_configured_embedding_gateway
from src.emailagent.adapters.llm.factory import get_configured_llm_gateway
from src.emailagent.db.session import async_session_factory
from src.emailagent.domain.models import (
    ChatQueryRequest,
    ChatQueryResponse,
    ThreadEmbeddingSyncResult
)
from src.emailagent.ports.embedding import EmbeddingGateway
from src.emailagent.ports.llm import LLMGateway
from src.emailagent.services.embedding import ThreadEmbeddingService
from src.emailagent.services.qa import MailboxQAService

router = APIRouter(prefix="/api/chat", tags=["Chat & Q&A Assistant"])


def get_embedding_service(
        embedding_gateway: EmbeddingGateway = Depends(get_configured_embedding_gateway)
) -> ThreadEmbeddingService:
    return ThreadEmbeddingService(
        embedding_gateway=embedding_gateway,
        session_factory=async_session_factory
    )


def get_qa_service(
        embedding_gateway: EmbeddingGateway = Depends(get_configured_embedding_gateway),
        llm_gateway: LLMGateway = Depends(get_configured_llm_gateway)
) -> MailboxQAService:
    return MailboxQAService(
        embedding_gateway=embedding_gateway,
        llm_gateway=llm_gateway,
        session_factory=async_session_factory
    )


@router.post("/sync-embeddings", response_model=ThreadEmbeddingSyncResult, summary="Sync vector for thread don't have embedding")
async def sync_embeddings(
        limit: int = 50,
        batch_size: int = 10,
        service: ThreadEmbeddingService = Depends(get_embedding_service)
):
    """Scan and compute vector embeddings for summarized threads using text-embedding-004."""
    return await service.sync_pending_embeddings(limit=limit, batch_size=batch_size)


@router.post("/ask", response_model=ChatQueryResponse, summary="Q&A email")
async def ask_mailbox(
        request: ChatQueryRequest,
        service: MailboxQAService = Depends(get_qa_service)
):
    """Ask natural language questions about emails, tasks, deadlines, and receive grounded answers with citations."""
    return await service.ask_mailbox(request=request)