import logging
from src.emailagent.adapters.embedding.gemini import GeminiEmbeddingGateway
from src.emailagent.config import settings
from src.emailagent.ports.embedding import EmbeddingGateway

logger = logging.getLogger("emailagent.adapters.embedding.factory")


def get_configured_embedding_gateway() -> EmbeddingGateway:
    provider = settings.EMBEDDING_PROVIDER.lower()
    if provider == "gemini":
        return GeminiEmbeddingGateway()
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER: '{provider}'")