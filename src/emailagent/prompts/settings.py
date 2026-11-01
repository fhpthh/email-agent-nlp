"""Application configuration adapter for pure prompt builders."""
from src.emailagent.config import settings
from src.emailagent.prompts.contexts import PromptBudgets


def configured_budgets() -> PromptBudgets:
    return PromptBudgets(
        analysis_body_chars=settings.PROMPT_ANALYSIS_BODY_CHARS,
        qa_snippet_chars=settings.PROMPT_QA_SNIPPET_CHARS,
        qa_messages_per_thread=settings.RAG_MAX_MESSAGES_PER_THREAD,
        history_messages=settings.PROMPT_HISTORY_MESSAGES,
        history_message_chars=settings.PROMPT_HISTORY_MESSAGE_CHARS,
    )
