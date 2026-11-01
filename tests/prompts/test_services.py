import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.emailagent.domain.models import (
    AnalyticsGeneratedAnswer, BatchThreadInsightModel, ChatQueryRequest, CitationItem,
    QAGeneratedAnswer, QueryFormulationResult, RetrievedThreadContext, EmailMessageSnippet,
)
from src.emailagent.services import qa, analysis

TID = '11111111-1111-4111-8111-111111111111'
NOW = datetime(2026, 10, 22, 18, tzinfo=timezone.utc)
BODY = 'Đã chốt hạn nộp báo cáo là ngày 25/10/2026.'


@asynccontextmanager
async def session_factory():
    yield SimpleNamespace(commit=AsyncMock())


def retrieved_thread():
    return RetrievedThreadContext(thread_id=TID, subject='Report', category='work', summary='summary', similarity_score=.9,
                                  last_message_at=NOW, messages=[EmailMessageSnippet(message_id='m', sender='a', date_sent=NOW, body_snippet=BODY)])


@pytest.mark.asyncio
@pytest.mark.parametrize('evidence,sufficient,expected', [(BODY, True, True), ('fabricated evidence', True, False), (BODY, False, False)])
async def test_qa_uses_real_builders_and_rejects_unverified_answers(monkeypatch, evidence, sufficient, expected):
    repo = SimpleNamespace(search_similar_threads=AsyncMock(return_value=[retrieved_thread()]))
    monkeypatch.setattr(qa, 'EmailRepository', lambda session: repo)
    llm = SimpleNamespace(extract_structured=AsyncMock(side_effect=[
        QueryFormulationResult(standalone_query='Hạn nộp?'),
        QAGeneratedAnswer(answer='ANSWER_FROM_MODEL', evidence_sufficient=sufficient,
                          citations=[CitationItem(thread_id=TID, evidence=evidence)]),
    ]))
    embedding = SimpleNamespace(embed_text=AsyncMock(return_value=[.1]))
    service = qa.MailboxQAService(embedding, llm, session_factory)
    result = await service.ask_mailbox(ChatQueryRequest(query='Hạn nộp?'))
    assert (result.answer == 'ANSWER_FROM_MODEL') == expected
    assert bool(result.citations) == expected
    prompt = llm.extract_structured.call_args.kwargs['prompt']
    assert prompt.user_request == 'Hạn nộp?'
    assert 'Hạn nộp?' not in prompt.evidence[0].text
    assert prompt.trace.prompt_id == 'qa'


@pytest.mark.asyncio
async def test_analytics_uses_resource_and_account_timezone(monkeypatch):
    repo = SimpleNamespace(
        get_account_info=AsyncMock(return_value={'timezone': 'America/New_York', 'email_address': 'owner@example.com', 'owner_name': 'Owner'}),
        get_analytics_summary=AsyncMock(return_value={'total_threads': 12}),
    )
    monkeypatch.setattr(qa, 'EmailRepository', lambda session: repo)
    llm = SimpleNamespace(extract_structured=AsyncMock(side_effect=[
        QueryFormulationResult(standalone_query='count', intent='analytics', analytics_metric='count_threads'),
        AnalyticsGeneratedAnswer(answer='Có 12 chuỗi thư.'),
    ]))
    service = qa.MailboxQAService(SimpleNamespace(), llm, session_factory)
    result = await service.ask_mailbox(ChatQueryRequest(query='count', account_id=UUID(TID)))
    assert result.answer == 'Có 12 chuỗi thư.'
    calls = llm.extract_structured.call_args_list
    assert calls[0].kwargs['prompt'].context['timezone'] == 'America/New_York'
    assert calls[1].kwargs['prompt'].trace.prompt_id == 'analytics'


@pytest.mark.asyncio
async def test_no_results_skips_answer_generation(monkeypatch):
    monkeypatch.setattr(qa, 'EmailRepository', lambda session: SimpleNamespace(search_similar_threads=AsyncMock(return_value=[])))
    llm = SimpleNamespace(extract_structured=AsyncMock(return_value=QueryFormulationResult(standalone_query='question')))
    service = qa.MailboxQAService(SimpleNamespace(embed_text=AsyncMock(return_value=[])), llm, session_factory)
    result = await service.ask_mailbox(ChatQueryRequest(query='question'))
    assert not result.citations
    assert llm.extract_structured.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('returned_id', [TID, '22222222-2222-4222-8222-222222222222'])
async def test_analysis_validates_ids_before_writing_and_uses_processing_time(monkeypatch, returned_id):
    old_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
    repo = SimpleNamespace(get_thread_emails=AsyncMock(return_value=[{'id': UUID(TID), 'date_sent': old_date, 'clean_body': BODY}]),
                           save_thread_insight_and_action_items=AsyncMock())
    monkeypatch.setattr(analysis, 'EmailRepository', lambda session: repo)
    llm = SimpleNamespace(extract_structured=AsyncMock(return_value=BatchThreadInsightModel(threads=[{
        'thread_id': returned_id, 'category': 'work', 'summary': 'summary', 'action_items': [],
    }])))
    service = analysis.ThreadAnalysisService(llm, session_factory)
    if returned_id != TID:
        with pytest.raises(ValueError, match='IDs'):
            await service._process_single_batch([UUID(TID)], 'owner@example.com', 'Owner', 'America/New_York')
        repo.save_thread_insight_and_action_items.assert_not_awaited()
    else:
        await service._process_single_batch([UUID(TID)], 'owner@example.com', 'Owner', 'America/New_York')
        repo.save_thread_insight_and_action_items.assert_awaited_once()
    prompt = llm.extract_structured.call_args.kwargs['prompt']
    assert datetime.fromisoformat(prompt.context['current_timestamp']).year > 2020
    message = json.loads(prompt.evidence[0].text)['messages'][0]
    assert message['date_sent'].startswith('2019-12-31T19:00:00-05:00')


@pytest.mark.asyncio
async def test_pending_batches_keep_account_context_separate(monkeypatch):
    other_tid = UUID('22222222-2222-4222-8222-222222222222')
    threads = [{'id': UUID(TID), 'account_id': 'a'}, {'id': other_tid, 'account_id': 'b'}]
    repo = SimpleNamespace(
        get_threads_with_pending_emails=AsyncMock(return_value=threads),
        get_thread_emails=AsyncMock(return_value=[{'clean_body': BODY}]),
        get_thread_account_info=AsyncMock(side_effect=[
            {'email_address': 'a@example.com', 'owner_name': 'A', 'timezone': 'Asia/Ho_Chi_Minh'},
            {'email_address': 'b@example.com', 'owner_name': 'B', 'timezone': 'America/New_York'},
        ]),
    )
    monkeypatch.setattr(analysis, 'EmailRepository', lambda session: repo)
    monkeypatch.setattr(analysis.asyncio, 'sleep', AsyncMock())
    service = analysis.ThreadAnalysisService(SimpleNamespace(), session_factory,
                                             rule_engine=SimpleNamespace(evaluate=lambda *args: None))
    service._process_single_batch = AsyncMock(side_effect=[[{'thread_id': TID}], [{'thread_id': str(other_tid)}]])
    result = await service.process_pending_threads(batch_size=10)
    assert result['succeeded'] == 2
    calls = service._process_single_batch.call_args_list
    assert calls[0].args == ([UUID(TID)], 'a@example.com', 'A', 'Asia/Ho_Chi_Minh')
    assert calls[1].args == ([other_tid], 'b@example.com', 'B', 'America/New_York')


@pytest.mark.asyncio
async def test_analysis_rejects_fabricated_action_evidence_before_persistence(monkeypatch):
    repo = SimpleNamespace(get_thread_emails=AsyncMock(return_value=[{'id': UUID(TID), 'clean_body': BODY}]),
                           save_thread_insight_and_action_items=AsyncMock())
    monkeypatch.setattr(analysis, 'EmailRepository', lambda session: repo)
    result = BatchThreadInsightModel(threads=[{
        'thread_id': TID, 'category': 'work', 'summary': 'summary',
        'action_items': [{'task': 'Do work', 'evidence': 'Invented quote'}],
    }])
    service = analysis.ThreadAnalysisService(SimpleNamespace(extract_structured=AsyncMock(return_value=result)), session_factory)
    with pytest.raises(ValueError, match='evidence'):
        await service._process_single_batch([UUID(TID)], 'owner@example.com', 'Owner', 'UTC')
    repo.save_thread_insight_and_action_items.assert_not_awaited()
