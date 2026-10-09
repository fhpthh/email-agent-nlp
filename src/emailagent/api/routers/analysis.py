from uuid import UUID

from fastapi import APIRouter, Depends

from src.emailagent.adapters.llm.factory import get_configured_llm_gateway
from src.emailagent.db.session import async_session_factory
from src.emailagent.ports.llm import LLMGateway
from src.emailagent.services.analysis import ThreadAnalysisService

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def get_analysis_service(
        llm: LLMGateway = Depends(get_configured_llm_gateway)
) -> ThreadAnalysisService:
    return ThreadAnalysisService(llm_gateway=llm, session_factory=async_session_factory)


@router.post("/process-pending", summary="Analytic threads email íd processing")
async def process_pending_emails(
        limit: int = 20,
        batch_size: int = 5,
        service: ThreadAnalysisService = Depends(get_analysis_service)
):
    return await service.process_pending_threads(limit=limit, batch_size=batch_size)


@router.post("/threads/{thread_id}", summary="Analytics thread id")
async def analyze_thread(
        thread_id: UUID,
        service: ThreadAnalysisService = Depends(get_analysis_service)
):
    return await service.analyze_thread(thread_id=thread_id)
