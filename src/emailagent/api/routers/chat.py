from fastapi import APIRouter, Depends, Request, Query

from src.emailagent.api.schemas.common import SuccessResponse, success
from src.emailagent.adapters.db.session import async_session_factory
from src.emailagent.adapters.embedding.factory import get_configured_embedding_gateway
from src.emailagent.adapters.llm.factory import get_configured_llm_gateway
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


@router.post("/sync-embeddings", response_model=SuccessResponse[ThreadEmbeddingSyncResult], summary="Synchronize missing thread embeddings")
async def sync_embeddings(
        request: Request,
        limit: int = Query(50, ge=1, le=1000),
        batch_size: int = Query(10, ge=1, le=100),
        service: ThreadEmbeddingService = Depends(get_embedding_service)
):
    """Scan and compute vector embeddings for summarized threads using text-embedding-004."""
    return success(request, await service.sync_pending_embeddings(limit=limit, batch_size=batch_size))


@router.post("/ask", response_model=SuccessResponse[ChatQueryResponse], summary="Q&A email")
async def ask_mailbox(
        payload: ChatQueryRequest,
        request: Request,
        service: MailboxQAService = Depends(get_qa_service)
):
    """Ask natural language questions about emails, tasks, deadlines, and receive grounded answers with citations."""
    return success(request, await service.ask_mailbox(request=payload))
