import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.emailagent.adapters.db.repositories import EmailRepository
from src.emailagent.config import settings
from src.emailagent.ports.provider import EmailProvider
from src.emailagent.utils.cleaner import EmailCleaner

logger = logging.getLogger("emailagent.services.ingestion")

class IngestionService:
    def __init__(self, provider: EmailProvider, session_factory: async_sessionmaker):
        self.provider = provider
        self.session_factory = session_factory

    async def sync_history(
        self,
        days_back: int = settings.DEFAULT_BACKFILL_DAYS,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Synchronize emails within a dynamic time window."""
        # 1. Resolve dynamic date range
        if date_from and date_to:
            since = date_from
            until = date_to
        else:
            until = datetime.now(timezone.utc)
            since = until - timedelta(days=days_back)

        logger.info(
            "Initiating email synchronization from %s to %s via provider: %s",
            since.isoformat(),
            until.isoformat(),
            self.provider.provider_name
        )
        emails, _ = await self.provider.fetch_history(since, until)

        # 2. Resolve account profile (Auto-fetched from provider or fallback)
        owner_email = settings.FALLBACK_OWNER_EMAIL
        owner_name = settings.FALLBACK_OWNER_NAME
        if hasattr(self.provider, "get_profile"):
            try:
                owner_email, owner_name = self.provider.get_profile()
            except Exception as exc:
                logger.warning("Failed to auto-resolve account profile from provider: %s", exc)

        ingested_count = 0
        async with self.session_factory() as session:
            async with session.begin():
                repo = EmailRepository(session)
                account_id = await repo.get_or_create_account(
                    email_address=owner_email,
                    owner_name=owner_name,
                    provider=self.provider.provider_name
                )
                for raw_mail in emails:
                    clean_text = EmailCleaner.clean_html(raw_mail.body_html, raw_mail.body_text)
                    thread_id = await repo.upsert_thread(
                        account_id=account_id,
                        provider_thread_id=raw_mail.provider_thread_id,
                        subject=raw_mail.subject,
                        last_message_at=raw_mail.date_sent
                    )
                    await repo.upsert_email(
                        account_id=account_id,
                        thread_id=thread_id,
                        email=raw_mail,
                        clean_body=clean_text
                    )
                    ingested_count += 1

        logger.info(
            "Synchronization completed successfully. Persisted %d emails for account %s.",
            ingested_count,
            owner_email
        )
        return {
            "status": "success",
            "owner_email": owner_email,
            "date_range": {
                "since": since.isoformat(),
                "until": until.isoformat()
            },
            "ingested_count": ingested_count
        }