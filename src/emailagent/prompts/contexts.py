"""Typed runtime context and explicit character budgets for external evidence."""
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field


class PromptBudgets(BaseModel):
    analysis_body_chars: int = Field(default=6000, ge=1)
    qa_snippet_chars: int = Field(default=2000, ge=1)
    qa_messages_per_thread: int = Field(default=3, ge=1)
    history_messages: int = Field(default=4, ge=0)
    history_message_chars: int = Field(default=4000, ge=1)


class RuntimeContext(BaseModel):
    current_timestamp: datetime
    timezone: str
    output_language: Literal["vi", "en"] = "vi"
    owner_name: str = "Mailbox Owner"
    owner_email: str | None = None

    @classmethod
    def create(cls, reference_date: datetime, timezone_str: str, **kwargs):
        try:
            tz = ZoneInfo(timezone_str)
        except (ZoneInfoNotFoundError, ValueError):
            tz = ZoneInfo("UTC")
        if reference_date.tzinfo is None:
            reference_date = reference_date.replace(tzinfo=timezone.utc)
        return cls(current_timestamp=reference_date.astimezone(tz), timezone=tz.key, **kwargs)


def clip(text: str | None, limit: int) -> dict:
    text = text or ""
    return {"text": text[:limit], "truncated": len(text) > limit, "original_chars": len(text)}
