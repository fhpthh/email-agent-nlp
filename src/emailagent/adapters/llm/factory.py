from functools import lru_cache

from src.emailagent.adapters.llm.gemini import GeminiLLMGateway
from src.emailagent.config import settings
from src.emailagent.ports.llm import LLMGateway


@lru_cache(maxsize=1)
def get_configured_llm_gateway() -> LLMGateway:
    provider = settings.LLM_GATEWAY_PROVIDER.lower()
    if provider == "gemini":
        return GeminiLLMGateway()
    else:
        raise ValueError(f"Unsupported LLM gateway provider: {provider}")
