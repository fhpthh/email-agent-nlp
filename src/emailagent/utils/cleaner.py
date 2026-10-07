import html

import logging
import re
from typing import Optional

logger = logging.getLogger("emailagent.utils.cleaner")


class EmailCleaner:
    @staticmethod
    def clean_html(html_content: Optional[str], fallback_text: str = "") -> str:
        """Loại bỏ thẻ HTML và chuyển đổi thành văn bản thuần sạch."""
        if not html_content:
            return fallback_text.strip()

        try:
            text = re.sub(r"<(script|style).*?>.*?</\1>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", text, flags=re.IGNORECASE)
            text = re.sub(r"<[^>]+>", "", text)
            text = html.unescape(text)
            cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
            if cleaned:
                return cleaned
        except Exception as exc:
            logger.warning("Error while cleaning html: %s", exc)

        return fallback_text.strip()
