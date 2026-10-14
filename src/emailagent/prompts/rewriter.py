from datetime import datetime
from typing import List

from src.emailagent.domain.models import ChatMessage


def build_query_formulation_prompt(
        chat_history: List[ChatMessage],
        latest_query: str,
        reference_date: datetime,
        timezone_str: str = "Asia/Ho_Chi_Minh"
) -> str:
    """Prompt cấu trúc cho Self-Querying, Intent Routing và Query Expansion."""
    history_lines = [
        f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
        for m in (chat_history or [])[-4:]
    ]
    history_text = "\n".join(history_lines) if history_lines else "None"
    date_str = reference_date.strftime("%Y-%m-%d (%A) %H:%M:%S UTC")

    return f"""You are a Master Search Query Formulator & Intent Classifier for an AI Email Assistant.

CURRENT TEMPORAL CONTEXT:
- Reference Timestamp: {date_str}
- User Timezone: {timezone_str}

CONVERSATION HISTORY:
{history_text}

USER QUESTION:
"{latest_query}"

YOUR TASKS:
1. INTENT CLASSIFICATION:
   - 'analytics': If the user asks to count, aggregate, or calculate totals across the mailbox (e.g. "bao nhiêu hóa đơn", "tổng cộng mấy task", "thống kê việc tuần này", "có bao nhiêu mail chưa đọc").
   - 'search': If the user seeks specific content, wants to find a particular email, ask about a deadline, or extract discussion facts.

2. QUERY CONDENSING & EXPANSION:
   - Resolve pronouns ("nó", "dự án đó", "người đó") using Conversation History.
   - Expand synonyms and bilingual domain terms (English & Vietnamese) into `expanded_keywords` for sparse keyword search (e.g., "dự án" -> ["project", "workspace", "team", "nhiệm vụ"]).

3. TEMPORAL & METADATA EXTRACTION (Self-Querying):
   - Resolve relative dates ("hôm qua", "tuần trước", "tháng 9", "quý 3") into absolute ISO 8601 timestamps for `date_after` and `date_before` based strictly on the Reference Timestamp.
   - Detect category if mentioned: 'work', 'finance_billing', 'meeting_calendar', 'report', 'personal', etc.
"""
