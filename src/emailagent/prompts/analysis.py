import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID
from xml.etree.ElementTree import Element, SubElement, tostring
from zoneinfo import ZoneInfo

from src.emailagent.ports.llm import PromptRequest, UntrustedPayload
from src.emailagent.prompts.contexts import PromptBudgets, RuntimeContext, clip
from src.emailagent.prompts.loader import prompt_loader
from src.emailagent.utils.security import to_local_datetime


def prepare_thread(thread_id: UUID, emails: list[dict[str, Any]], runtime: RuntimeContext,
                   budgets: PromptBudgets) -> dict:
    tz = ZoneInfo(runtime.timezone)
    messages = []
    for mail in emails:
        sent = to_local_datetime(mail.get("date_sent"), tz)
        messages.append({
            "message_id": str(mail.get("id", "")), "sender": mail.get("sender"),
            "recipients": mail.get("recipients"), "cc": mail.get("cc"),
            "subject": clip(mail.get("subject"), 500),
            "date_sent": sent.isoformat() if sent else None,
            "body": clip(mail.get("clean_body"), budgets.analysis_body_chars),
        })
    messages.sort(key=lambda message: message["date_sent"] or "")
    return {"thread_id": str(thread_id), "messages": messages}


def build_analysis_prompt(threads: dict[str, list[dict]], runtime: RuntimeContext,
                          budgets: PromptBudgets | None = None, version: str | None = None) -> PromptRequest:
    system, task, trace = prompt_loader.load("analysis", version)
    budgets = budgets or PromptBudgets()
    evidence = [UntrustedPayload(content_id=tid, text=json.dumps(
        prepare_thread(UUID(tid), emails, runtime, budgets), ensure_ascii=False,
    )) for tid, emails in threads.items()]
    return PromptRequest(system_instruction=system, user_request=task,
                         context=runtime.model_dump(mode="json"), evidence=evidence, trace=trace)


def build_analysis_system_instruction(reference_date=None, owner_email=None, owner_name=None,
                                      timezone_str="Asia/Ho_Chi_Minh", version=None, **kwargs) -> str:
    """Compatibility helper. Runtime fields now belong to PromptRequest.context."""
    return prompt_loader.load("analysis", version)[0]


def format_thread_messages_to_xml(thread_id: UUID, emails: list[dict],
                                  timezone_str: str = "Asia/Ho_Chi_Minh") -> str:
    """Legacy serializer for external callers; production builders use JSON evidence."""
    runtime = RuntimeContext.create(datetime.now(timezone.utc), timezone_str)
    data = prepare_thread(thread_id, emails, runtime, PromptBudgets())
    root = Element("thread", id=str(thread_id))
    for message in data["messages"]:
        node = SubElement(root, "untrusted_message", id=message["message_id"])
        node.text = json.dumps(message, ensure_ascii=False)
    return tostring(root, encoding="unicode")


get_analysis_static_system_instruction = build_analysis_system_instruction
