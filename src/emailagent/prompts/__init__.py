from typing import List, Optional

from src.emailagent.prompts.analysis import (
    get_analysis_static_system_instruction,
    format_thread_messages_to_xml
)
from src.emailagent.prompts.qa import (
    get_qa_static_system_instruction,
    build_qa_user_context_block
)
from src.emailagent.prompts.rewriter import (
    build_query_rewriter_prompt
)


def build_thread_embedding_text(
        subject: str,
        category: str,
        summary: str,
        action_items: Optional[List[str]] = None,
        sender: Optional[str] = None
) -> str:
    sender_block = f"Người gửi: {sender}\n" if sender else ""
    tasks_block = f"\nNhiệm vụ: {'; '.join(action_items)}" if action_items else ""
    return (
        f"{sender_block}"
        f"Tiêu đề: {subject}\n"
        f"Phân loại: {category}\n"
        f"Nội dung chính: {summary}"
        f"{tasks_block}"
    ).strip()


build_analysis_system_instruction = get_analysis_static_system_instruction
build_qa_system_instruction = get_qa_static_system_instruction

__all__ = [
    # Q&A RAG
    "get_qa_static_system_instruction",
    "build_qa_user_context_block",
    "build_qa_system_instruction",

    # Analysis & Batch
    "get_analysis_static_system_instruction",
    "build_analysis_system_instruction",
    "format_thread_messages_to_xml",

    # Multi-turn Rewriter
    "build_query_rewriter_prompt",

    # Embedding Text Generator
    "build_thread_embedding_text"
]
