from typing import List
from src.emailagent.domain.models import ChatMessage


def build_query_rewriter_prompt(
        chat_history: List[ChatMessage],
        latest_query: str
) -> str:
    """Prompt chỉ định LLM chuyển đổi câu hỏi phụ thuộc thành truy vấn độc lập."""
    history_lines = []
    for msg in chat_history:
        sender_role = "User" if msg.role == "user" else "Assistant"
        history_lines.append(f"{sender_role}: {msg.content}")

    history_text = "\n".join(history_lines)

    return f"""You are a Search Query Reformulator for an email RAG system.

RECENT CONVERSATION HISTORY:
{history_text}

NEW USER QUESTION:
"{latest_query}"

TASK:
1. Resolve ambiguous pronouns or implicit references (e.g., "he", "that project", "that task", "the deadline").
2. Reformulate the new user question into a SINGLE, STANDALONE search query in Vietnamese.
3. If the user question is already standalone, keep it unchanged.
4. STRICT RULE: Output ONLY the reformulated query. Do not add explanations or quotes."""