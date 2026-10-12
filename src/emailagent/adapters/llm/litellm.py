import asyncio
import logging
from typing import Optional, Sequence, Type

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from src.emailagent.config import settings
from src.emailagent.ports.llm import LLMGateway, T, UntrustedPayload

logger = logging.getLogger("emailagent.adapters.llm")

DEFAULT_TIMEOUT_SECONDS: float = 30.0
DEFAULT_MAX_RETRIES: int = 3
BACKOFF_BASE_SECONDS: float = 2.0

RETRYABLE_EXCEPTIONS = (
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    InternalServerError,
)


class LiteLLMGateway(LLMGateway):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.api_key = api_key or getattr(settings, "LITELLM_API_KEY", None) or settings.LLM_API_KEY
        raw_url = base_url or getattr(settings, "LITELLM_BASE_URL", None) or settings.LLM_BASE_URL
        self.model_name = model_name or getattr(settings, "LITELLM_MODEL_NAME", None) or settings.LLM_MODEL_NAME
        self.timeout = timeout
        self.max_retries = max_retries

        if not raw_url or not self.api_key:
            logger.error("GATEWAY_INIT_FAILED: missing base_url or api_key")
            raise ValueError("LITELLM gateway requires base_url and api_key")

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

    def _render_payloads(self, payloads: Sequence[UntrustedPayload]) -> str:
        return "\n\n".join(
            f'<untrusted_message id="{item.content_id}">\n{item.text}\n</untrusted_message>'
            for item in payloads
        )

    async def extract_structured(
        self,
        schema: Type[T],
        system_instruction: str,
        untrusted_contents: Sequence[UntrustedPayload],
    ) -> T:
        prompt_content = self._render_payloads(untrusted_contents)
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt_content},
        ]

        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self._client.beta.chat.completions.parse(
                    model=self.model_name,
                    messages=messages,
                    response_format=schema,
                    extra_body={"drop_params": True},
                )
                message = response.choices[0].message

                if getattr(message, "parsed", None) and isinstance(message.parsed, schema):
                    return message.parsed

                if message.content:
                    return schema.model_validate_json(message.content)

                raise ValueError("EMPTY_OR_INVALID_COMPLETION")

            except RETRYABLE_EXCEPTIONS as exc:
                last_exception = exc
                if attempt < self.max_retries:
                    backoff = attempt * BACKOFF_BASE_SECONDS
                    logger.warning(
                        "LLM_RETRY: attempt=%d/%d backoff=%.1fs error=%s",
                        attempt,
                        self.max_retries,
                        backoff,
                        type(exc).__name__,
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.error("LLM_RETRIES_EXHAUSTED: attempts=%d model=%s", self.max_retries, self.model_name)
                    raise last_exception

            except Exception as exc:
                logger.error("LLM_FATAL_ERROR: type=%s detail=%s", type(exc).__name__, str(exc))
                raise exc

        if last_exception:
            raise last_exception
        raise RuntimeError("LLM_EXECUTION_FAILED")

    async def generate_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
    ) -> str:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            extra_body={"drop_params": True},
        )
        return response.choices[0].message.content or ""