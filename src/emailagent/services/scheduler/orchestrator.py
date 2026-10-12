import asyncio
import logging
import time
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.emailagent.adapters.embedding.factory import get_configured_embedding_gateway
from src.emailagent.adapters.llm.factory import get_configured_llm_gateway
from src.emailagent.adapters.provider.factory import get_configured_email_provider
from src.emailagent.config import settings
from src.emailagent.db.session import async_session_factory
from src.emailagent.services.analysis import ThreadAnalysisService
from src.emailagent.services.embedding import ThreadEmbeddingService
from src.emailagent.services.ingestion import IngestionService

logger = logging.getLogger("emailagent.scheduler.orchestrator")


class EmailSyncOrchestrator:

    def __init__(self, session_factory: Optional[async_sessionmaker] = None):
        self._session_factory = session_factory or async_session_factory

    async def execute_cycle(self) -> Dict[str, Any]:

        start_time = time.perf_counter()
        logger.info("Starting background email synchronization cycle...")

        cycle_summary: Dict[str, Any] = {
            "status": "success",
            "ingested_count": 0,
            "rule_filtered": 0,
            "llm_processed": 0,
            "embeddings_synced": 0,
            "duration_seconds": 0.0,
            "error": None,
        }

        try:
            # 1. Step 1: Ingestion Phase (Pull recent emails from active provider)
            provider = get_configured_email_provider()
            ingestion_service = IngestionService(
                provider=provider,
                session_factory=self._session_factory
            )
            ingest_result = await ingestion_service.sync_history(
                days_back=settings.SCHEDULER_DAYS_BACK
            )
            cycle_summary["ingested_count"] = ingest_result.get("ingested_count", 0)
            logger.info("Ingestion completed: %d emails persisted.", cycle_summary["ingested_count"])

            # 2. Step 2: Analysis Phase (Rule Engine Fast-Path -> Gemini Cognitive Batch)
            llm_gateway = get_configured_llm_gateway()
            analysis_service = ThreadAnalysisService(
                llm_gateway=llm_gateway,
                session_factory=self._session_factory
            )
            analysis_result = await analysis_service.process_pending_threads(
                limit=settings.SCHEDULER_BATCH_LIMIT,
                batch_size=settings.SCHEDULER_CHUNK_SIZE
            )
            cycle_summary["rule_filtered"] = analysis_result.get("rule_filtered", 0)
            cycle_summary["llm_processed"] = analysis_result.get("llm_processed", 0)
            logger.info(
                "Analysis completed: %d rule-filtered, %d LLM-analyzed.",
                cycle_summary["rule_filtered"],
                cycle_summary["llm_processed"]
            )

            # Small breather pause to respect API rate limits before embedding
            await asyncio.sleep(1.0)

            embedding_gateway = get_configured_embedding_gateway()
            embedding_service = ThreadEmbeddingService(
                embedding_gateway=embedding_gateway,
                session_factory=self._session_factory
            )
            embed_result = await embedding_service.sync_pending_embeddings(
                limit=settings.SCHEDULER_BATCH_LIMIT,
                batch_size=settings.SCHEDULER_CHUNK_SIZE
            )
            cycle_summary["embeddings_synced"] = embed_result.synced
            logger.info("Embedding synchronization completed: %d threads vectorized.",
                        cycle_summary["embeddings_synced"])

        except Exception as exc:
            cycle_summary["status"] = "failed"
            cycle_summary["error"] = str(exc)
            logger.error("Background sync cycle encountered an error: %s", exc, exc_info=True)

        finally:
            cycle_summary["duration_seconds"] = round(time.perf_counter() - start_time, 2)
            logger.info(
                "Background sync cycle finished in %.2fs with status '%s'.",
                cycle_summary["duration_seconds"],
                cycle_summary["status"]
            )

        return cycle_summary
