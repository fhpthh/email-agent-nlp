from uuid import UUID

from fastapi import APIRouter, Depends, Request, Query

from src.emailagent.api.schemas.common import SuccessResponse, success
from src.emailagent.api.schemas.analysis import BatchAnalysisData, ThreadAnalysisData
from src.emailagent.adapters.db.session import async_session_factory
from src.emailagent.adapters.llm.factory import get_configured_llm_gateway
from src.emailagent.ports.llm import LLMGateway
from src.emailagent.services.analysis import ThreadAnalysisService

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def get_analysis_service(
        llm: LLMGateway = Depends(get_configured_llm_gateway)
) -> ThreadAnalysisService:
    return ThreadAnalysisService(llm_gateway=llm, session_factory=async_session_factory)


@router.post("/process-pending", summary="Analyze pending email threads", response_model=SuccessResponse[BatchAnalysisData])
async def process_pending_emails(
        request: Request,
        limit: int = Query(20, ge=1, le=1000),
        batch_size: int = Query(5, ge=1, le=100),
        service: ThreadAnalysisService = Depends(get_analysis_service)
):
    return success(request, await service.process_pending_threads(limit=limit, batch_size=batch_size))


@router.post("/threads/{thread_id}", summary="Analyze an email thread", response_model=SuccessResponse[ThreadAnalysisData])
async def analyze_thread(
        thread_id: UUID,
        request: Request,
        service: ThreadAnalysisService = Depends(get_analysis_service)
):
    return success(request, await service.analyze_thread(thread_id=thread_id))
