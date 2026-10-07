from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from sqlalchemy.ext.asyncio import async_sessionmaker

import logging
from src.emailagent.adapters.db.repositories import EmailRepository
from src.emailagent.ports.provider import EmailProvider
from src.emailagent.utils.cleaner import EmailCleaner

logger = logging.getLogger("emailagent.services.ingestion")


class IngestionService:
    def __init__(self, provider: EmailProvider, session_factory: async_sessionmaker):
        self.provider = provider
        self.session_factory = session_factory

    async def sync_history(
            self,
            owner_email: str,
            owner_name: str,
            days_back: int = 7) -> Dict[str, Any]:
        until = datetime.now(timezone.utc)
        since = until - timedelta(days=days_back)

        logger.info(f"Syncing history from {owner_email} to {owner_name}")

        emails, _ = await self.provider.fetch_history(since, until)

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
        logger.info(f"Sync history from {owner_email} to {owner_name}")
        return {
            "status": "success",
            "account_id": str(account_id),
            "ingested_count": ingested_count,
        }
