from abc import ABC, abstractmethod
from typing import List


class EmbeddingGateway(ABC):
    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        """Tạo vector embedding cho một đoạn văn bản đơn lẻ."""
        pass

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Tạo vector embedding cho danh sách nhiều đoạn văn bản cùng lúc."""
        pass
