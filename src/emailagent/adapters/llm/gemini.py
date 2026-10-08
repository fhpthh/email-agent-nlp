import asyncio
import logging
from typing import TypeVar, Optional, Type, Sequence

from google import genai
from google.genai import types
from pydantic import BaseModel

from src.emailagent.config import settings
from src.emailagent.ports.llm import LLMGateway, UntrustedPayload

logger = logging.getLogger("emailagent.adapters.llm.gemini")
T = TypeVar("T", bound=BaseModel)


class GeminiLLMGateway(LLMGateway):
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._model_name = model_name or settings.LLM_MODEL_NAME
        self._client = genai.Client(api_key=self._api_key)

    async def extract_structured(
        self,
        schema: Type[T],
        system_instruction: str,
        untrusted_contents: Sequence[UntrustedPayload]
    ) -> T:
        xml_parts = []
        for item in untrusted_contents:
            xml_parts.append(
                f'<untrusted_message id="{item.content_id}">\n{item.text}\n</untrusted_message>'
            )
        prompt_content = "\n\n".join(xml_parts)

        logger.debug(
            "Calling Gemini (%s) with Structured Output schema: %s for %d payloads",
            self._model_name, schema.__name__, len(untrusted_contents)
        )

        # Cơ chế Auto-Retry 3 lần nếu Google bị nghẽn 503
        max_retries = 3
        last_exception = None

        for attempt in range(1, max_retries + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model_name,
                    contents=prompt_content,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=schema,
                        temperature=0.1,
                    )
                )

                if hasattr(response, "parsed") and response.parsed is not None:
                    if isinstance(response.parsed, schema):
                        return response.parsed
                return schema.model_validate_json(response.text)

            except Exception as exc:
                last_exception = exc
                err_str = str(exc)
                # Nếu gặp 503 (quá tải tạm thời), đợi 2-3 giây rồi thử lại
                if ("503" in err_str or "UNAVAILABLE" in err_str) and attempt < max_retries:
                    wait_time = attempt * 2  # Thử lại sau 2s, 4s
                    logger.warning("Gemini server is busy (503). Retrying in %ds (Attempt %d/%d)...", wait_time, attempt, max_retries)
                    await asyncio.sleep(wait_time)
                else:
                    raise last_exception

        raise last_exception

    async def generate_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None
    ) -> str:
        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
            )
        )
        return response.text or ""