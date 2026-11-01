"""Provider-neutral prompt contract. JSON boundaries are structural, not authorization."""
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class UntrustedPayload(BaseModel):
    content_id: str
    text: str


class PromptTrace(BaseModel):
    prompt_id: str
    version: str
    bundle_hash: str
    output_schema_version: str


class PromptRequest(BaseModel):
    system_instruction: str
    user_request: str
    context: dict[str, Any] = Field(default_factory=dict)
    evidence: list[UntrustedPayload] = Field(default_factory=list)
    trace: PromptTrace

    def user_content(self) -> str:
        # Serialize once, keeping quotes/tags in user-controlled strings as data.
        # Evidence precedes the current request; instructions stay in the system message.
        return json.dumps({
            "context": self.context,
            "untrusted_evidence": [item.model_dump() for item in self.evidence],
            "user_request": self.user_request,
        }, ensure_ascii=False)


def log_prompt_call(prompt: PromptRequest, model: str, schema: Type[BaseModel]) -> None:
    schema_hash = hashlib.sha256(json.dumps(schema.model_json_schema(), sort_keys=True).encode()).hexdigest()
    logger.info(
        "LLM_CALL prompt_id=%s version=%s bundle_hash=%s model=%s schema=%s schema_version=%s schema_hash=%s",
        prompt.trace.prompt_id, prompt.trace.version, prompt.trace.bundle_hash, model,
        schema.__name__, prompt.trace.output_schema_version, schema_hash,
    )


class LLMGateway(ABC):
    @abstractmethod
    async def extract_structured(self, schema: Type[T], prompt: PromptRequest) -> T:
        """Generate a validated result using separate instructions, request and evidence."""
        raise NotImplementedError

    @abstractmethod
    async def generate_response(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Low-level free-text generation for callers without a structured contract."""
        raise NotImplementedError
