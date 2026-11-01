from datetime import datetime
from uuid import UUID
from typing import Literal, Optional
from pydantic import BaseModel, Field
from src.emailagent.config import settings


class DateRange(BaseModel):
    since: datetime
    until: datetime


class BackfillData(BaseModel):
    status: Literal["success"]
    owner_email: str
    date_range: DateRange
    ingested_count: int


class EmailData(BaseModel):
    id: UUID
    provider_message_id: str
    sender: str
    subject: str | None
    date_sent: datetime | None
    status: str


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


