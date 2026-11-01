import json
from datetime import datetime
from typing import List

from src.emailagent.domain.models import ChatMessage
from src.emailagent.ports.llm import PromptRequest, UntrustedPayload
from src.emailagent.prompts.contexts import PromptBudgets, RuntimeContext, clip
from src.emailagent.prompts.loader import prompt_loader


def build_query_formulation_prompt(chat_history: List[ChatMessage], latest_query: str,
                                   reference_date: datetime, timezone_str: str = "Asia/Ho_Chi_Minh",
                                   version: str | None = None, budgets: PromptBudgets | None = None) -> PromptRequest:
    system, _, trace = prompt_loader.load("rewriter", version)
    runtime = RuntimeContext.create(reference_date, timezone_str)
    budgets = budgets or PromptBudgets()
    selected = (chat_history or [])[-budgets.history_messages:] if budgets.history_messages else []
    history = [{"role": message.role, "content": clip(message.content, budgets.history_message_chars)}
               for message in selected]
    return PromptRequest(
        system_instruction=system, user_request=latest_query, context=runtime.model_dump(mode="json"),
        evidence=[UntrustedPayload(content_id="conversation_history", text=json.dumps({
            "messages": history, "messages_omitted": len(chat_history or []) > len(selected),
        }, ensure_ascii=False))], trace=trace,
    )


build_query_rewriter_prompt = build_query_formulation_prompt
