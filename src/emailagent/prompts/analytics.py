import json

from src.emailagent.ports.llm import PromptRequest, UntrustedPayload
from src.emailagent.prompts.contexts import RuntimeContext
from src.emailagent.prompts.loader import prompt_loader


def build_analytics_prompt(stats: dict, filters: dict, runtime: RuntimeContext,
                           user_query: str, version: str | None = None) -> PromptRequest:
    system, _, trace = prompt_loader.load("analytics", version)
    return PromptRequest(
        system_instruction=system, user_request=user_query, context=runtime.model_dump(mode="json"),
        evidence=[UntrustedPayload(content_id="database_statistics", text=json.dumps({
            "statistics": stats, "filters": filters,
        }, ensure_ascii=False))], trace=trace,
    )
