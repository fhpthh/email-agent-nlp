from fastapi import APIRouter, Depends, Request, Query

from src.emailagent.api.schemas.common import SuccessResponse, success
from src.emailagent.api.schemas.sync import BackfillData, BackfillRequest, EmailData
from src.emailagent.adapters.db.repositories import EmailRepository
from src.emailagent.adapters.db.session import async_session_factory
from src.emailagent.adapters.provider.factory import get_configured_email_provider
from src.emailagent.config import settings
from src.emailagent.ports.provider import EmailProvider
from src.emailagent.services.ingestion import IngestionService

router = APIRouter(prefix="/api/sync", tags=["Sync"])


def get_ingestion_service(
        provider: EmailProvider = Depends(get_configured_email_provider)
) -> IngestionService:
    return IngestionService(provider=provider, session_factory=async_session_factory)


@router.post("/backfill", summary="Trigger historical email synchronization", response_model=SuccessResponse[BackfillData])
async def trigger_backfill(
        request: Request,
        payload: BackfillRequest = BackfillRequest(),
        service: IngestionService = Depends(get_ingestion_service)
):
    """
    Synchronize historical emails into PostgreSQL:
    - If empty payload: Defaults to the configured default window (30 days).
    - If days_back provided: Syncs the past N days.
    - If date_from & date_to provided: Syncs the exact explicit time window.
    """
    result = await service.sync_history(
        days_back=payload.days_back or settings.DEFAULT_BACKFILL_DAYS,
        date_from=payload.date_from,
        date_to=payload.date_to
    )
    return success(request, result)


@router.get("/emails", summary="List ingested emails from database", response_model=SuccessResponse[list[EmailData]])
async def list_ingested_emails(request: Request, limit: int = Query(50, ge=1, le=1000)):
    """Retrieve ingested email metadata stored in PostgreSQL."""
    async with async_session_factory() as session:
        repo = EmailRepository(session)
        return success(request, await repo.list_emails(limit=limit))
