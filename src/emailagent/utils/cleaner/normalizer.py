import re
import unicodedata


class TextNormalizer:
    _HIDDEN_CHARS_REGEX = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff\u00ad\u034f]")

    @classmethod
    def normalize_text(cls, text: str) -> str:
        if not text:
            return ""

        normalized = unicodedata.normalize("NFC", text)
        cleaned = cls._HIDDEN_CHARS_REGEX.sub("", normalized)
        return cleaned.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
