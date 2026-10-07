from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict

from src.emailagent.config import settings
from src.emailagent.ports.provider import EmailProvider


def _build_fake_provider() -> EmailProvider:
    from src.emailagent.adapters.provider.fake import FakeEmailProvider
    mock_path = Path("tests/data/mock_emails.json")
    return FakeEmailProvider(mock_file_path=mock_path)


def _build_gmail_provider() -> EmailProvider:
    from src.emailagent.adapters.provider.gmail import GmailProvider

    creds_path = Path(settings.GMAIL_CREDENTIALS_PATH)
    token_path = Path(settings.GMAIL_TOKEN_PATH)

    if not creds_path.exists() and not token_path.exists():
        raise FileNotFoundError(
            f"Gmail credentials not found at {creds_path} or {token_path}. "
            "Please download credentials.json from Google Cloud Console."
        )

    return GmailProvider(
        credentials_path=creds_path,
        token_path=token_path,
    )


# Registry mapping
_PROVIDER_REGISTRY: Dict[str, Callable[[], EmailProvider]] = {
    "fake": _build_fake_provider,
    "gmail": _build_gmail_provider,
    # "outlook": _build_outlook_provider,
    # "imap": _build_imap_provider,
}


@lru_cache(maxsize=1)
def get_configured_email_provider() -> EmailProvider:
    provider_name = settings.ACTIVE_EMAIL_PROVIDER.lower()
    builder = _PROVIDER_REGISTRY.get(provider_name)

    if not builder:
        supported = list(_PROVIDER_REGISTRY.keys())
        raise ValueError(
            f"Unsupported ACTIVE_EMAIL_PROVIDER: '{provider_name}'. Supported providers: {supported}"
        )

    return builder()