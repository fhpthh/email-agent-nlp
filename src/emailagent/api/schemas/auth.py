from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class AuthCallbackData(BaseModel):
    connected_email: str | None = None


class AuthStatusData(BaseModel):
    # Local token validity only; this does not query Google for revocation.
    authenticated: bool = False
    state: Literal["not_connected", "valid", "expired", "invalid"] = "not_connected"
    expired: bool = False
    has_refresh_token: bool = False
    expiry: datetime | None = None
