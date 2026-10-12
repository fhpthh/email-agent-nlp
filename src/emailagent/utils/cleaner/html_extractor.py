import html
import logging
import re
from typing import Tuple
import lxml.html
from lxml_html_clean import Cleaner

from src.emailagent.utils.cleaner.constants import QUOTE_CSS_SELECTORS

logger = logging.getLogger("emailagent.utils.cleaner.html")


class DOMExtractor:
    """
    DOM-level HTML parser using lxml to isolate quotes and render structured content.
    """

    _CLEANER = Cleaner(
        scripts=True,
        javascript=True,
        comments=True,
        style=True,
        inline_style=False,
        links=False,
        meta=True,
        page_structure=False,
        processing_instructions=True,
        embedded=True,
        frames=True,
        forms=True,
        annoying_tags=True,
        remove_unknown_tags=False,
    )

    @classmethod
    def extract_and_isolate_quotes(cls, html_content: str) -> Tuple[str, str]:
        try:
            cleaned_html = cls._CLEANER.clean_html(html_content)
            tree = lxml.html.fromstring(cleaned_html)
        except Exception as exc:
            logger.error(exc)
            return html.unescape(re.sub(r"<[^>]+>", " ", html_content)), ""

        extracted_quotes = []

        # Bóc tách các container quote dựa trên CSS Selectors
        for selector in QUOTE_CSS_SELECTORS:
            for element in tree.cssselect(selector):
                quote_text = element.text_content().strip()
                if quote_text:
                    extracted_quotes.append(quote_text)
                parent = element.getparent()
                if parent is not None:
                    parent.remove(element)

        # Chuyển bảng dữ liệu thật thành định dạng bảng Markdown
        for table in tree.cssselect("table"):
            rows = []
            for tr in table.cssselect("tr"):
                cells = [td.text_content().strip() for td in tr.cssselect("td, th")]
                cells = [c for c in cells if c]
                if cells:
                    rows.append(" | ".join(cells))
            if len(rows) >= 2:
                table_md = "\n" + "\n".join(rows) + "\n"
                table.text = table_md
                for child in list(table):
                    table.remove(child)

        main_text = tree.text_content()
        quotes_bundle = "\n\n---\n\n".join(extracted_quotes)
        return main_text, quotes_bundle