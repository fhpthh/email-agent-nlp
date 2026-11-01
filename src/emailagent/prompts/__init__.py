from typing import List, Optional

from src.emailagent.prompts.analytics import build_analytics_prompt
from src.emailagent.prompts.contexts import RuntimeContext, PromptBudgets
from src.emailagent.prompts.analysis import (
    build_analysis_prompt,
    get_analysis_static_system_instruction,
    build_analysis_system_instruction,
    format_thread_messages_to_xml
)
from src.emailagent.prompts.loader import prompt_loader
from src.emailagent.prompts.qa import (
    build_qa_prompt,
    get_qa_static_system_instruction,
    build_qa_user_context_block,
    build_qa_system_instruction
)
from src.emailagent.prompts.rewriter import (
    build_query_formulation_prompt,
    build_query_rewriter_prompt
)


def build_thread_embedding_text(
        subject: str,
        category: str,
        summary: str,
        action_items: Optional[List[str]] = None,
        sender: Optional[str] = None,
        body_snippet: Optional[str] = None
) -> str:
    """Hàm tạo nội dung giàu ngữ nghĩa (Enriched) để băm Vector Embedding."""
    sender_block = f"Người gửi: {sender}\n" if sender else ""
    tasks_block = f"\nNhiệm vụ: {'; '.join(action_items)}" if action_items else ""
    snippet_block = f"\nNội dung thư: {body_snippet}" if body_snippet else ""
    return (
        f"{sender_block}"
        f"Tiêu đề: {subject}\n"
        f"Phân loại: {category}\n"
        f"Nội dung chính: {summary}"
        f"{tasks_block}"
        f"{snippet_block}"
    ).strip()


__all__ = [
    "build_analysis_prompt", "build_qa_prompt", "build_analytics_prompt",
    "RuntimeContext", "PromptBudgets",
    # Q&A RAG
    "get_qa_static_system_instruction",
    "build_qa_user_context_block",
    "build_qa_system_instruction",

    # Analysis & Ingestion
    "get_analysis_static_system_instruction",
    "build_analysis_system_instruction",
    "format_thread_messages_to_xml",

    # Multi-turn Rewriter & Self-Querying
    "build_query_rewriter_prompt",
    "build_query_formulation_prompt",

    # Embedding Helper & Loader
    "build_thread_embedding_text",
    "prompt_loader",
]
