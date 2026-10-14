import logging
import re
from pathlib import Path
from typing import Set

logger = logging.getLogger("emailagent.utils.stopwords")

DEFAULT_STOPWORDS: Set[str] = {
    "và", "của", "là", "thì", "mà", "ở", "tại", "cho", "được", "bị", "bởi",
    "do", "với", "nhưng", "tuy", "hoặc", "hay", "các", "những", "cái", "chiếc",
    "này", "đó", "kia", "ấy", "vậy", "như", "ra", "vào", "từ", "đến", "trong",
    "cùng", "theo", "về", "lên", "xuống", "qua", "lại", "để", "rồi", "đã", "sẽ",
    "đang", "nhé", "nha", "ạ", "xin", "nữa", "khi", "lúc", "nơi", "cũng", "đều",
    "vì", "rằng", "rất", "quá", "lắm"
}

_STOPWORDS_CACHE: Set[str] = set()


def _load_stopwords() -> Set[str]:
    global _STOPWORDS_CACHE
    if _STOPWORDS_CACHE:
        return _STOPWORDS_CACHE

    stopwords_path = Path(__file__).resolve().parent.parent / "resources" / "vietnamese_stopwords.txt"
    if stopwords_path.exists():
        try:
            with open(stopwords_path, "r", encoding="utf-8") as f:
                words = {
                    line.strip().lower()
                    for line in f
                    if line.strip() and not line.strip().startswith("#")
                }
                if words:
                    _STOPWORDS_CACHE = words
                    logger.debug("Loaded %d stopwords from %s", len(words), stopwords_path)
                    return _STOPWORDS_CACHE
        except Exception as e:
            logger.warning("Failed to read stopwords file %s: %s. Using default.", stopwords_path, e)

    _STOPWORDS_CACHE = DEFAULT_STOPWORDS
    return _STOPWORDS_CACHE


def remove_vietnamese_stopwords(text: str) -> str:
    """
    Loại bỏ các hư từ tiếng Việt khỏi chuỗi truy vấn trước khi tìm kiếm FTS.
    Giữ lại toàn bộ từ phủ định (không, chưa), từ thời gian, và keyword nghiệp vụ.
    """
    if not text:
        return ""

    stopwords = _load_stopwords()
    tokens = text.strip().split()
    filtered_tokens = [tok for tok in tokens if tok.lower() not in stopwords]

    if not filtered_tokens:
        return text.strip()

    cleaned = " ".join(filtered_tokens)
    return re.sub(r"\s+", " ", cleaned).strip()
