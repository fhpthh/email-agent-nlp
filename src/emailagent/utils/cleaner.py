import html
import logging
import re
from typing import Optional

import trafilatura
from email_reply_parser import EmailReplyParser

logger = logging.getLogger("emailagent.utils.cleaner")


class EmailCleaner:
    @staticmethod
    def _extract_text_from_html(html_content: str) -> str:
        """Bóc tách văn bản thuần từ HTML, loại bỏ thẻ style, script, tracker."""
        try:
            extracted = trafilatura.extract(
                html_content,
                include_comments=False,
                include_tables=True,
                no_fallback=False
            )
            if extracted and extracted.strip():
                return extracted
        except Exception as exc:
            logger.warning("Trafilatura extraction failed: %s", exc)

        text = re.sub(r"<(script|style).*?>.*?</\1>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        return html.unescape(text)

    @classmethod
    def clean_html(cls, html_content: Optional[str], fallback_text: str = "") -> str:

        # Bước 1: Trích xuất nội dung văn bản
        if html_content and html_content.strip():
            raw_text = cls._extract_text_from_html(html_content)
        else:
            raw_text = fallback_text or ""

        raw_text = raw_text.strip()
        if not raw_text:
            return ""

        # Bước 2: Sử dụng EmailReplyParser để cắt bỏ quote tiếng Anh và chữ ký (-- ...)
        try:
            parsed_reply = EmailReplyParser.parse_reply(raw_text)
            final_text = parsed_reply if parsed_reply.strip() else raw_text
        except Exception as exc:
            logger.warning("EmailReplyParser failed: %s. Using raw text.", exc)
            final_text = raw_text

        # Bước 3: Dọn dẹp
        final_text = re.sub(r"\r\n", "\n", final_text)
        final_text = re.sub(r"\n{3,}", "\n\n", final_text)

        return final_text.strip()
