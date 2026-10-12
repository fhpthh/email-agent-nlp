from src.emailagent.utils.cleaner.constants import (
    DISCLAIMER_REGEX,
    MIN_BODY_LENGTH_GUARD,
    SIGN_OFF_REGEX,
)


class NoiseStripper:
    @classmethod
    def strip_disclaimers_and_signatures(cls, text: str) -> str:

        cleaned_text = text

        # 1. Cắt disclaimer bảo mật ở cuối văn bản
        disclaimer_match = DISCLAIMER_REGEX.search(cleaned_text)
        if disclaimer_match:
            candidate = cleaned_text[:disclaimer_match.start()].strip()
            if len(candidate) >= MIN_BODY_LENGTH_GUARD:
                cleaned_text = candidate

        # 2. Quét chữ ký từ nửa sau của email
        lines = [line.strip() for line in cleaned_text.splitlines()]
        total_lines = len(lines)
        cutoff_index = total_lines

        start_scan = max(0, int(total_lines * 0.40))
        for idx in range(start_scan, total_lines):
            if SIGN_OFF_REGEX.match(lines[idx]):
                candidate_body = "\n".join(lines[:idx]).strip()
                if len(candidate_body) >= MIN_BODY_LENGTH_GUARD:
                    cutoff_index = idx
                    break

        return "\n".join(lines[:cutoff_index]).strip()
