import json
from datetime import datetime
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

from src.emailagent.domain.models import RetrievedThreadContext
from src.emailagent.ports.llm import PromptRequest, UntrustedPayload
from src.emailagent.prompts.contexts import PromptBudgets, RuntimeContext, clip
from src.emailagent.prompts.loader import prompt_loader
from src.emailagent.utils.security import to_local_datetime


def get_qa_static_system_instruction(version: str | None = None) -> str:
    return prompt_loader.load("qa", version)[0]


def prepare_qa_evidence(contexts: list[RetrievedThreadContext], runtime: RuntimeContext,
                        budgets: PromptBudgets) -> tuple[list[UntrustedPayload], dict[str, list[str]], dict]:
    evidence, raw_texts, dates = [], {}, []
    tz = ZoneInfo(runtime.timezone)
    for thread in contexts:
        messages, snippets = [], []
        ordered = sorted(thread.messages, key=lambda item: (
            to_local_datetime(item.date_sent, tz).timestamp() if item.date_sent else float("-inf")
        ))
        for message in ordered[-budgets.qa_messages_per_thread:]:
            snippet = clip(message.body_snippet, budgets.qa_snippet_chars)
            sent = to_local_datetime(message.date_sent, tz)
            snippets.append(snippet["text"])
            messages.append({
                "message_id": message.message_id, "sender": message.sender,
                "date_sent": sent.isoformat() if sent else None, "snippet": snippet,
            })
        raw_texts[str(thread.thread_id)] = snippets
        last_message = to_local_datetime(thread.last_message_at, tz)
        if last_message:
            dates.append(last_message)
        data = {
            "thread_id": str(thread.thread_id), "subject": clip(thread.subject, 200),
            "summary": clip(thread.summary, 500), "category": thread.category,
            "message_scope": "recent_snippets",
            "provided_messages_omitted": len(ordered) > len(messages), "messages": messages,
        }
        evidence.append(UntrustedPayload(content_id=str(thread.thread_id), text=json.dumps(data, ensure_ascii=False)))
    metrics = {
        "returned_thread_count": len(contexts), "scope": "retrieved_subset",
        "earliest_thread_last_message_at": min(dates).isoformat() if dates else None,
        "latest_thread_last_message_at": max(dates).isoformat() if dates else None,
    }
    return evidence, raw_texts, metrics


def build_qa_prompt(contexts: list[RetrievedThreadContext], runtime: RuntimeContext, user_query: str,
                    budgets: PromptBudgets | None = None, version: str | None = None
                    ) -> tuple[PromptRequest, dict[str, list[str]]]:
    system, _, trace = prompt_loader.load("qa", version)
    evidence, raw_texts, metrics = prepare_qa_evidence(contexts, runtime, budgets or PromptBudgets())
    context = runtime.model_dump(mode="json")
    context["retrieval"] = metrics
    return PromptRequest(system_instruction=system, user_request=user_query, context=context,
                         evidence=evidence, trace=trace), raw_texts


def build_qa_user_context_block(retrieved_contexts: List[RetrievedThreadContext], reference_date: datetime,
                                owner_name: str, owner_email: str, timezone_str: str = "Asia/Ho_Chi_Minh",
                                user_query: str = "", version: str | None = None) -> Tuple[str, Dict[str, str]]:
    """Compatibility serializer; services should use build_qa_prompt and per-message evidence."""
    runtime = RuntimeContext.create(reference_date, timezone_str, owner_name=owner_name, owner_email=owner_email)
    prompt, snippets = build_qa_prompt(retrieved_contexts, runtime, user_query, version=version)
    return prompt.user_content(), {tid: "\n".join(parts) for tid, parts in snippets.items()}


build_qa_system_instruction = get_qa_static_system_instruction
