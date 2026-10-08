import logging
import types
from typing import TypeVar, Optional, Type, Sequence

from google import genai
from openai import BaseModel

from emailagent.config import settings
from emailagent.ports.llm import LLMGateway, UntrustedPayload

logger = logging.getLogger("emailagent.adapters.llm.gemini")
T = TypeVar("T", bound=BaseModel)


class GeminiLLMGateway(LLMGateway):
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL_NAME
        self.client = genai.Client(api_key=self.api_key)

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

    async def generate_structured(
            self,
            prompt: str,
            system_instruction: Optional[str] = None
    ) -> str:
        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            content=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
            )
        )
        return response.text or ""
