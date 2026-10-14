import html
import re
import unicodedata
from datetime import datetime, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.emailagent.domain.models import CitationItem

_WS = re.compile(r"\s+")


def escape_text(text: str) -> str:
    """Escape nội dung text bên trong thẻ XML (<, >, &)."""
    return html.escape(text or "", quote=False)


def escape_attr(text: str) -> str:
    """Escape thuộc tính XML (bao gồm cả dấu nháy kép quote=True)."""
    return html.escape(text or "", quote=True)


def to_local_datetime(dt: Optional[datetime], tz: ZoneInfo) -> Optional[datetime]:
    """Quy đổi datetime sang múi giờ địa phương (Coi DB là UTC nếu là naive datetime)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)


def _norm(s: str) -> str:
    """Chuẩn hóa chuỗi để so khớp: Unescape HTML, NFC Unicode, xóa khoảng trắng và lowercase."""
    s = html.unescape(s or "")
    s = unicodedata.normalize("NFC", s)
    return _WS.sub("", s).casefold()


def verify_and_filter_citations(
        citations: List[CitationItem],
        thread_texts: Dict[str, str],  # Map: thread_id -> raw snippet thực tế mà LLM đã đọc
        min_len: int = 8,
        max_len: int = 300,
) -> List[CitationItem]:
    """
    Xác thực trích dẫn: Đảm bảo evidence thực sự nằm trong raw snippet của chính thread đó.
    Loại bỏ hoàn toàn trích dẫn bịa đặt và trích dẫn gán sai thread.
    """
    norm_texts = {str(tid): _norm(t) for tid, t in thread_texts.items()}
    seen, verified = set(), []

    for item in citations or []:
        tid = str(item.thread_id)
        ev = _norm(item.evidence)

        if tid not in norm_texts or not (min_len <= len(ev) <= max_len):
            continue

        if ev in norm_texts[tid] and (tid, ev) not in seen:
            seen.add((tid, ev))
            verified.append(item)

    return verified