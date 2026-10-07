from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.emailagent.adapters.db.repositories import EmailRepository
from src.emailagent.adapters.providers.fake import FakeEmailProvider
from src.emailagent.db.session import async_session_factory
from src.emailagent.services.ingestion.py import IngestionService

router = APIRouter(prefix="/api/sync", tags=["Sync"])


# DTO nhận vào cho request backfill
class BackfillRequest(BaseModel):
    owner_email: str = Field(default="user@vccorp.vn", description="Email of account owner")
    owner_name: str = Field(default="Nguyen Van A", description="Display name of owner")
    days_back: int = Field(default=7, ge=1, le=30, description="Number of days to sync back")


# Factory cấp phát IngestionService
def get_ingestion_service() -> IngestionService:
    mock_path = Path("tests/data/mock_emails.json")
    provider = FakeEmailProvider(mock_path)
    return IngestionService(provider=provider, session_factory=async_session_factory)


@router.post("/backfill")
async def trigger_backfill(
    payload: BackfillRequest,
    service: IngestionService = Depends(get_ingestion_service)
):
    """Kích hoạt quét và đồng bộ email cũ vào database."""
    result = await service.sync_history(
        owner_email=payload.owner_email,
        owner_name=payload.owner_name,
        days_back=payload.days_back
    )
    return result


@router.get("/emails")
async def list_ingested_emails(limit: int = 20):
    """Xem danh sách các email đã được ingest trong CSDL."""
    async with async_session_factory() as session:
        repo = EmailRepository(session)
        return await repo.list_emails(limit=limit)