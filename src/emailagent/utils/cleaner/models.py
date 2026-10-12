from dataclasses import dataclass


@dataclass(frozen=True)
class CleanedEmailPayLoad:
    body: str
    quoted_history: str = ""
    is_forward: bool = False
    raw_char_count: int = 0
    clean_char_count: int = 0


