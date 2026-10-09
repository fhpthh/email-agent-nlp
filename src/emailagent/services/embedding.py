import logging
from typing import List
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.emailagent.adapters.db.repositories import EmailRepository
from src.emailagent.domain.models import ThreadEmbeddingSyncResult
from src.emailagent.ports.embedding import EmbeddingGateway
from src.emailagent.utils.prompt import build_thread_embedding_text

logger = logging.getLogger("emailagent.services.embedding")


class ThreadEmbeddingService:
    """Application Service for synchronizing vector embeddings of summarized threads."""

    def __init__(self, embedding_gateway: EmbeddingGateway, session_factory: async_sessionmaker):
        self.embedding_gateway = embedding_gateway
        self.session_factory = session_factory

    async def sync_pending_embeddings(self, limit: int = 50, batch_size: int = 10) -> ThreadEmbeddingSyncResult:
        """Scan threads without embeddings, compute vectors and persist in database."""
        async with self.session_factory() as session:
            repo = EmailRepository(session)
            threads = await repo.get_threads_missing_embeddings(limit=limit)

            if not threads:
                logger.info("No threads pending embedding synchronization.")
                return ThreadEmbeddingSyncResult(total_found=0, synced=0, failed=0)

            logger.info("Found %d threads pending vector embeddings.", len(threads))
            synced_count = 0
            failed_count = 0

            # Chia nhỏ danh sách thread thành từng chunk batch_size để gọi model embedding
            for i in range(0, len(threads), batch_size):
                chunk = threads[i:i + batch_size]
                texts_to_embed = [
                    build_thread_embedding_text(
                        subject=t.get("subject") or "(Không có tiêu đề)",
                        category=t.get("category") or "uncategorized",
                        summary=t.get("summary") or ""
                    )
                    for t in chunk
                ]

                try:
                    vectors = await self.embedding_gateway.embed_batch(texts_to_embed)
                    for thread_data, vector in zip(chunk, vectors):
                        await repo.update_thread_embedding(thread_id=thread_data["id"], embedding=vector)
                        synced_count += 1
                except Exception as exc:
                    logger.error("Failed to generate embeddings for chunk of %d threads: %s", len(chunk), exc)
                    failed_count += len(chunk)

            await session.commit()
            return ThreadEmbeddingSyncResult(
                total_found=len(threads),
                synced=synced_count,
                failed=failed_count
            )