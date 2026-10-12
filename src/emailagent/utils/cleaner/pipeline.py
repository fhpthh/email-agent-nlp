import logging
import re
from typing import Optional

from src.emailagent.utils.cleaner.constants import MAX_INPUT_BYTES_LIMIT
from src.emailagent.utils.cleaner.html_extractor import DOMExtractor
from src.emailagent.utils.cleaner.models import CleanedEmailPayLoad
from src.emailagent.utils.cleaner.noise_stripper import NoiseStripper
from src.emailagent.utils.cleaner.normalizer import TextNormalizer
from src.emailagent.utils.cleaner.thread_splitter import ThreadSplitter

logger = logging.getLogger("emailagent.utils.cleaner.pipeline")


class EmailCleaner:

    @classmethod
    def clean_and_split(
            cls,
            html_content: Optional[str],
            fallback_text: str = "",
    ) -> CleanedEmailPayLoad:

        raw_source = html_content or fallback_text or ""
        raw_char_count = len(raw_source)

        if raw_char_count > MAX_INPUT_BYTES_LIMIT:
            logger.warning("Email exceeds max byte limit, truncating source")
            raw_source = raw_source[:MAX_INPUT_BYTES_LIMIT]

        dom_quote = ""
        # Bóc tách tầng DOM
        if html_content and html_content.strip():
            main_text, dom_quote = DOMExtractor.extract_and_isolate_quotes(html_content)
        else:
            main_text = fallback_text or ""

        # Chuẩn hóa ngôn ngữ và Unicode
        normalized_text = TextNormalizer.normalize_text(main_text)
        normalized_dom_quote = TextNormalizer.normalize_text(dom_quote)

        # Phân tách Thread Reply & kiểm tra Forward
        body_candidate, text_quote, is_forward = ThreadSplitter.split_reply_and_forward(normalized_text)

        # Cắt bỏ chữ ký và disclaimer có Guard
        final_body = NoiseStripper.strip_disclaimers_and_signatures(body_candidate)

        # Chuẩn hóa khoảng trắng
        final_body = re.sub(r"[ \t]+", " ", final_body)
        final_body = re.sub(r"\n{3,}", "\n\n", final_body).strip()

        full_quote = "\n\n".join(q for q in [normalized_dom_quote, text_quote] if q).strip()

        # Guard hoàn nguyên nếu body bị trống
        if not final_body and full_quote:
            final_body = full_quote
            full_quote = ""

        clean_len = len(final_body)
        logger.debug("Cleaned email: raw=%d -> clean=%d", raw_char_count, clean_len)

        return CleanedEmailPayLoad(
            body=final_body,
            quoted_history=full_quote,
            is_forward=is_forward,
            raw_char_count=raw_char_count,
            clean_char_count=clean_len,
        )

    @classmethod
    def clean_html(cls, html_content: Optional[str], fallback_text: str = "") -> str:

        payload = cls.clean_and_split(html_content, fallback_text)
        return payload.body
