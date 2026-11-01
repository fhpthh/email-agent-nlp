import logging
import os
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from time import monotonic

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from oauthlib.oauth2 import OAuth2Error
from requests.exceptions import RequestException

from src.emailagent.config import settings
from src.emailagent.core.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
SESSION_TTL_SECONDS = 600
MAX_SESSIONS = 1000

# Scope changes are validated explicitly below. HTTP is only allowed in local development.
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
if settings.ENV.lower() == "development":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
else:
    os.environ.pop("OAUTHLIB_INSECURE_TRANSPORT", None)


@dataclass(frozen=True)
class OAuthSession:
    verifier: str
    expires_at: float


class OAuthSessionStore:
    """Bounded, expiring, one-use sessions. Replace with shared storage for multiple workers."""
    def __init__(self):
        self._sessions: dict[str, OAuthSession] = {}
        self._lock = Lock()

    def put(self, state: str, verifier: str) -> None:
        with self._lock:
            now = monotonic()
            self._sessions = {key: item for key, item in self._sessions.items() if item.expires_at > now}
            if len(self._sessions) >= MAX_SESSIONS:
                self._sessions.pop(next(iter(self._sessions)))
            self._sessions[state] = OAuthSession(verifier, now + SESSION_TTL_SECONDS)

    def consume(self, state: str | None, browser_state: str | None) -> OAuthSession:
        if not state or not browser_state or not secrets.compare_digest(state, browser_state):
            raise AppError(ErrorCode.AUTH_INVALID_STATE)
        with self._lock:
            session = self._sessions.pop(state, None)
        if session is None or session.expires_at <= monotonic():
            raise AppError(ErrorCode.AUTH_INVALID_STATE)
        return session


class GmailAuthService:
    def __init__(self, sessions: OAuthSessionStore):
        self.sessions = sessions

    def _flow(self, state: str | None = None) -> Flow:
        credentials_path = Path(settings.GMAIL_CREDENTIALS_PATH)
        if not credentials_path.is_file():
            raise AppError(ErrorCode.AUTH_NOT_CONFIGURED)
        try:
            return Flow.from_client_secrets_file(
                str(credentials_path), scopes=SCOPES,
                redirect_uri=settings.GMAIL_REDIRECT_URI, state=state,
                autogenerate_code_verifier=True,
            )
        except (OSError, ValueError) as exc:
            raise AppError(ErrorCode.AUTH_NOT_CONFIGURED) from exc

    def login(self) -> tuple[str, str]:
        flow = self._flow()
        url, state = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
        if not flow.code_verifier:
            raise AppError(ErrorCode.INTERNAL_ERROR)
        self.sessions.put(state, flow.code_verifier)
        return url, state

    def callback(self, code: str | None, state: str | None, error: str | None, browser_state: str | None) -> str | None:
        session = self.sessions.consume(state, browser_state)
        if error:
            raise AppError(ErrorCode.AUTH_DENIED)
        if not code:
            raise AppError(ErrorCode.AUTH_MISSING_CODE)
        flow = self._flow(state)
        flow.code_verifier = session.verifier
        try:
            flow.fetch_token(code=code)
        except (OAuth2Error, RequestException) as exc:
            raise AppError(ErrorCode.AUTH_EXCHANGE_FAILED) from exc
        creds = flow.credentials
        granted = creds.granted_scopes if creds.granted_scopes is not None else creds.scopes
        if not set(SCOPES).issubset(set(granted or [])):
            raise AppError(ErrorCode.AUTH_SCOPE_REQUIRED)
        self._save_token(creds)
        try:
            service = build("gmail", "v1", credentials=creds)
            return service.users().getProfile(userId="me").execute().get("emailAddress")
        except Exception:
            logger.warning("Unable to retrieve Gmail profile after authorization", exc_info=True)
            return None

    @staticmethod
    def _save_token(creds: Credentials) -> None:
        target = Path(settings.GMAIL_TOKEN_PATH)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(creds.to_json())
            # NamedTemporaryFile is owner-readable/writable only; replace atomically.
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def credentials(self) -> Credentials | None:
        path = Path(settings.GMAIL_TOKEN_PATH)
        if not path.exists():
            return None
        try:
            return Credentials.from_authorized_user_file(str(path), SCOPES)
        except (ValueError, OSError) as exc:
            raise AppError(ErrorCode.AUTH_TOKEN_INVALID) from exc


auth_service = GmailAuthService(OAuthSessionStore())


def get_auth_service() -> GmailAuthService:
    return auth_service
