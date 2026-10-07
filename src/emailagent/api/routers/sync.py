from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.emailagent.adapters.db.repositories import EmailRepository
from src.emailagent.adapters.provider.factory import get_configured_email_provider
from src.emailagent.config import settings
from src.emailagent.db.session import async_session_factory
from src.emailagent.ports.provider import EmailProvider
from src.emailagent.services.ingestion import IngestionService

router = APIRouter(prefix="/api/sync", tags=["Sync"])


class BackfillRequest(BaseModel):
    days_back: Optional[int] = Field(
        default=settings.DEFAULT_BACKFILL_DAYS,
        ge=1,
        le=settings.MAX_BACKFILL_DAYS,
        description=f"Days to look back (default: {settings.DEFAULT_BACKFILL_DAYS}, max: {settings.MAX_BACKFILL_DAYS})"
    )
    date_from: Optional[datetime] = Field(
        default=None,
        description="Explicit start date (ISO 8601: YYYY-MM-DDTHH:MM:SSZ). Overrides days_back if provided."
    )
    date_to: Optional[datetime] = Field(
        default=None,
        description="Explicit end date (ISO 8601: YYYY-MM-DDTHH:MM:SSZ)."
    )


def get_ingestion_service(
        provider: EmailProvider = Depends(get_configured_email_provider)
) -> IngestionService:
    return IngestionService(provider=provider, session_factory=async_session_factory)


@router.post("/backfill", summary="Trigger historical email synchronization")
async def trigger_backfill(
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
    return result


@router.get("/emails", summary="List ingested emails from database")
async def list_ingested_emails(limit: int = 50):
    """Retrieve ingested email metadata stored in PostgreSQL."""
    async with async_session_factory() as session:
        repo = EmailRepository(session)
        return await repo.list_emails(limit=limit)
