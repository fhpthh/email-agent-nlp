import asyncio
import logging
from typing import List, Optional

from google import genai
from google.genai import types

from src.emailagent.config import settings
from src.emailagent.ports.embedding import EmbeddingGateway

logger = logging.getLogger("emailagent.adapters.embedding.gemini")


class GeminiEmbeddingGateway(EmbeddingGateway):
    """Adapter implementing EmbeddingGateway using Google Gemini gemini-embedding-001."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self._client = genai.Client(api_key=self._api_key)

    async def embed_text(self, text: str) -> List[float]:
        """Generate a single 768-dimensional vector embedding."""
        vectors = await self.embed_batch([text])
        return vectors[0] if vectors else []

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate vector embeddings for multiple texts with exponential backoff retry."""
        if not texts:
            return []

        logger.debug("Generating embeddings for %d texts using model %s", len(texts), self._model_name)

        # Cấu hình ép kích thước vector về 768 chiều khớp với schema PostgreSQL
        embed_config = types.EmbedContentConfig(
            output_dimensionality=settings.VECTOR_DIMENSION
        )

        max_attempts = 3
        backoff_delay = 1.0

        for attempt in range(1, max_attempts + 1):
            try:
                response = await self._client.aio.models.embed_content(
                    model=self._model_name,
                    contents=texts,
                    config=embed_config
                )

                results = []
                for emb in response.embeddings:
                    results.append(list(emb.values))
                return results

            except Exception as exc:
                is_transient = any(
                    err in str(exc) for err in ["503", "429", "RESOURCE_EXHAUSTED", "UNAVAILABLE"]
                )
                if is_transient and attempt < max_attempts:
                    logger.warning(
                        "Gemini embedding transient error on attempt %d/%d: %s. Retrying in %.1fs...",
                        attempt, max_attempts, exc, backoff_delay
                    )
                    await asyncio.sleep(backoff_delay)
                    backoff_delay *= 2.0
                else:
                    logger.error("Failed to generate embeddings after attempt %d/%d: %s", attempt, max_attempts, exc)
                    raise
        return []