from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse

from src.emailagent.api.schemas.auth import AuthCallbackData, AuthStatusData
from src.emailagent.api.schemas.common import SuccessResponse, success
from src.emailagent.config import settings
from src.emailagent.services.auth import GmailAuthService, SESSION_TTL_SECONDS, get_auth_service

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
STATE_COOKIE = "emailagent_oauth_state"


@router.get("/login", summary="Start Google OAuth authorization", response_class=RedirectResponse, status_code=307)
def login(service: GmailAuthService = Depends(get_auth_service)) -> RedirectResponse:
    url, state = service.login()
    response = RedirectResponse(url)
    response.set_cookie(
        STATE_COOKIE, state, max_age=SESSION_TTL_SECONDS, httponly=True,
        secure=settings.ENV.lower() != "development", samesite="lax", path="/api/auth",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/callback", summary="Complete Google OAuth authorization", response_model=SuccessResponse[AuthCallbackData])
def auth_callback(
    request: Request, response: Response,
    code: str | None = None, state: str | None = None, error: str | None = None,
    service: GmailAuthService = Depends(get_auth_service),
):
    email = service.callback(code, state, error, request.cookies.get(STATE_COOKIE))
    response.delete_cookie(STATE_COOKIE, path="/api/auth")
    response.headers["Cache-Control"] = "no-store"
    return success(request, AuthCallbackData(connected_email=email))


@router.get("/status", summary="Inspect local Gmail token validity", response_model=SuccessResponse[AuthStatusData])
def auth_status(request: Request, response: Response, service: GmailAuthService = Depends(get_auth_service)):
    """Inspect local credentials; this endpoint does not check revocation with Google."""
    response.headers["Cache-Control"] = "no-store"
    creds = service.credentials()
    if creds is None:
        return success(request, AuthStatusData())
    return success(request, AuthStatusData(
        authenticated=creds.valid,
        state="valid" if creds.valid else "expired" if creds.expired else "invalid",
        expired=creds.expired, has_refresh_token=bool(creds.refresh_token), expiry=creds.expiry,
    ))
