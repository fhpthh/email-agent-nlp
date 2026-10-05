from abc import ABC, abstractmethod
from typing import Sequence, Type, TypeVar, Optional
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


# Nội dung email được bọc an toàn (chống Prompt Injection)
class UntrustedPayload(BaseModel):
    content_id: str
    text: str


# Cổng giao tiếp tương tác với mô hình ngôn ngữ lớn (LLM)
class LLMGateway(ABC):
    @abstractmethod
    async def extract_structured(
        self,
        schema: Type[T],
        system_instruction: str,
        untrusted_contents: Sequence[UntrustedPayload]
    ) -> T:
        """Ép LLM trích xuất dữ liệu trả về đúng schema Pydantic."""
        pass

    @abstractmethod
    async def generate_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None
    ) -> str:
        """Sinh câu trả lời thông thường cho Agent."""
        pass