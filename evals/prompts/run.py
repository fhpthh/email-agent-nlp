"""Offline fixture validation by default; --live explicitly invokes the configured provider."""
import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Support execution as `python evals/prompts/run.py` from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.emailagent.domain.models import BatchThreadInsightModel, QAGeneratedAnswer, QueryFormulationResult, RetrievedThreadContext
from src.emailagent.prompts.analysis import build_analysis_prompt
from src.emailagent.prompts.contexts import RuntimeContext
from src.emailagent.prompts.qa import build_qa_prompt
from src.emailagent.prompts.rewriter import build_query_formulation_prompt
from src.emailagent.utils.security import verify_and_filter_citations

CASES_PATH = Path(__file__).with_name('cases.json')
SCHEMAS = {'qa': QAGeneratedAnswer, 'analysis': BatchThreadInsightModel, 'rewriter': QueryFormulationResult}


def prepare(case):
    now = datetime.fromisoformat(case['reference_date'])
    runtime = RuntimeContext.create(now, case['timezone'], owner_email='owner@example.com')
    if case['domain'] == 'qa':
        return build_qa_prompt([RetrievedThreadContext.model_validate(t) for t in case['threads']], runtime, case['query'])
    if case['domain'] == 'rewriter':
        return build_query_formulation_prompt([], case['query'], now, case['timezone']), {}
    threads = {tid: [{**m, 'date_sent': datetime.fromisoformat(m['date_sent'])} for m in messages]
               for tid, messages in case['threads'].items()}
    return build_analysis_prompt(threads, runtime), {}


def matches_subset(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and matches_subset(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(matches_subset(a, b) for a, b in zip(actual, expected))
    if isinstance(actual, str) and isinstance(expected, str) and "T" in expected:
        try:
            return datetime.fromisoformat(actual.replace("Z", "+00:00")) == datetime.fromisoformat(expected.replace("Z", "+00:00"))
        except ValueError:
            pass
    return actual == expected


def evaluate(case, output, snippets):
    checks = {'expected_fields': matches_subset(output.model_dump(mode='json'), case['expected'])}
    if case['domain'] == 'qa':
        valid = verify_and_filter_citations(output.citations, snippets)
        checks['citation_membership'] = len(valid) == len(output.citations)
        checks['citation_required'] = bool(valid) if output.evidence_sufficient else not output.citations
        checks['injection_canary_absent'] = 'SECRET_PWNED' not in output.answer
    return checks


async def run(live=False):
    gateway = None
    model_id = None
    if live:
        from src.emailagent.adapters.llm.factory import get_configured_llm_gateway
        from src.emailagent.config import settings
        gateway = get_configured_llm_gateway()
        model_id = settings.LLM_MODEL_NAME if settings.LLM_PROVIDER == 'gemini' else settings.LITELLM_MODEL_NAME
    rows = []
    for case in json.loads(CASES_PATH.read_text()):
        prompt, snippets = prepare(case)
        schema = SCHEMAS[case['domain']]
        try:
            output = await gateway.extract_structured(schema, prompt) if gateway else schema.model_validate(case['reference_output'])
            checks = evaluate(case, output, snippets)
            rows.append({'case_id': case['id'], 'trace': prompt.trace.model_dump(), 'checks': checks, 'passed': all(checks.values())})
        except Exception as exc:
            rows.append({'case_id': case['id'], 'trace': prompt.trace.model_dump(), 'passed': False, 'error_type': type(exc).__name__})
    return {
        'mode': 'live_model_eval' if live else 'fixture_validation_only',
        'created_at': datetime.now(timezone.utc).isoformat(), 'model_id': model_id,
        'dataset_hash': hashlib.sha256(CASES_PATH.read_bytes()).hexdigest(),
        'passed': sum(row['passed'] for row in rows), 'total': len(rows), 'cases': rows,
        'limitations': 'Checks cover expected fields and quote membership, not semantic entailment of all claims. No model quality measurement in fixture-only mode.',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', help='Call the configured LLM; incurs provider usage.')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = asyncio.run(run(args.live))
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(serialized + '\n')
    print(serialized)
    raise SystemExit(0 if report['passed'] == report['total'] else 1)
