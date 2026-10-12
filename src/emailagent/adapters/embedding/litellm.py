import asyncio
import logging
from typing import List, Optional, Sequence

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from src.emailagent.config import settings
from src.emailagent.ports.embedding import EmbeddingGateway

logger = logging.getLogger("emailagent.adapters.embedding.litellm")

DEFAULT_TIMEOUT_SECONDS: float = 30.0
DEFAULT_MAX_RETRIES: int = 3
BACKOFF_BASE_SECONDS: float = 2.0

RETRYABLE_EXCEPTIONS = (
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    InternalServerError,
)


class LiteLLMEmbeddingGateway(EmbeddingGateway):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        dimensions: Optional[int] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.api_key = api_key or getattr(settings, "LITELLM_API_KEY", None) or settings.LLM_API_KEY
        raw_url = base_url or getattr(settings, "LITELLM_BASE_URL", None) or settings.LLM_BASE_URL
        self.model_name = (
            model_name
            or getattr(settings, "EMBEDDING_MODEL_NAME", None)
            or getattr(settings, "LITELLM_MODEL_NAME", None)
        )
        self.dimensions = dimensions or getattr(settings, "VECTOR_DIMENSION", None)
        self.timeout = timeout
        self.max_retries = max_retries

        if not raw_url or not self.api_key:
            logger.error("EMBEDDING_INIT_FAILED: missing base_url or api_key")
            raise ValueError("LiteLLM embedding gateway requires base_url and api_key")

        self.base_url = self._normalize_endpoint(raw_url)
        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

    @staticmethod
    def _normalize_endpoint(url: str) -> str:
        clean = url.strip().rstrip("/")
        return clean if clean.endswith("/v1") else f"{clean}/v1"

    async def embed_text(self, text: str) -> List[float]:
        vectors = await self.embed_batch([text])
        return vectors[0] if vectors else []

    async def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []

        payload_kwargs = {
            "model": self.model_name,
            "input": list(texts),
            "extra_body": {"drop_params": True},
        }
        if self.dimensions:
            payload_kwargs["dimensions"] = self.dimensions

        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self._client.embeddings.create(**payload_kwargs)
                sorted_data = sorted(response.data, key=lambda item: item.index)
                return [item.embedding for item in sorted_data]

            except RETRYABLE_EXCEPTIONS as exc:
                last_exception = exc
                if attempt < self.max_retries:
                    backoff = attempt * BACKOFF_BASE_SECONDS
                    logger.warning(
                        "EMBEDDING_RETRY: attempt=%d/%d backoff=%.1fs error=%s",
                        attempt,
                        self.max_retries,
                        backoff,
                        type(exc).__name__,
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.error(
                        "EMBEDDING_RETRIES_EXHAUSTED: attempts=%d model=%s",
                        self.max_retries,
                        self.model_name,
                    )
                    raise last_exception

            except Exception as exc:
                logger.error("EMBEDDING_FATAL_ERROR: type=%s detail=%s", type(exc).__name__, str(exc))
                raise exc

        if last_exception:
            raise last_exception
        raise RuntimeError("EMBEDDING_EXECUTION_FAILED")