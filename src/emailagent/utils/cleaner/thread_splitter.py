from typing import Tuple

from src.emailagent.utils.cleaner.constants import FORWARD_HEADER_REGEX, TEXT_REPLY_REGEXES, MIN_BODY_LENGTH_GUARD


class ThreadSplitter():
    @classmethod
    def split_reply_and_forward(cls, text: str) -> Tuple[str, str, bool]:
        is_forward = bool(FORWARD_HEADER_REGEX.search(text))

        if is_forward:
            return text, "", True

        candidate_body = text
        isolated_quote = ""

        for pattern in TEXT_REPLY_REGEXES:
            match = pattern.search(candidate_body)
            if match:
                head = candidate_body[:match.start()].strip()
                tail = candidate_body[match.end():].strip()

                if len(head) >= MIN_BODY_LENGTH_GUARD:
                    candidate_body = head
                    isolated_quote = tail
                    break
        return candidate_body, isolated_quote, False
