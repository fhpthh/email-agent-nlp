"""Exercise every JSON route using dependency overrides instead of external services."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.emailagent.api.main import app
from src.emailagent.api.routers import analysis, chat, sync


@pytest.fixture
def client():
    previous = dict(app.dependency_overrides)
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_health_contract(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['data']['status'] == 'healthy'
    assert response.json()['meta']['request_id'] == response.headers['x-request-id']


def test_chat_contract(client):
    service = SimpleNamespace(ask_mailbox=AsyncMock(return_value={
        'query': 'my emails', 'answer': 'No matching emails.', 'citations': [], 'relevant_threads_count': 0,
    }))
    app.dependency_overrides[chat.get_qa_service] = lambda: service
    response = client.post('/api/chat/ask', json={'query': 'my emails'})
    assert response.status_code == 200
    assert response.json()['data']['answer'] == 'No matching emails.'
    assert service.ask_mailbox.call_args.kwargs['request'].query == 'my emails'
    invalid = client.post('/api/chat/ask', json={'query': 'x'})
    assert invalid.status_code == 422
    assert invalid.json()['errors'][0]['location'] == ['body', 'query']


def test_embedding_contract(client):
    service = SimpleNamespace(sync_pending_embeddings=AsyncMock(return_value={'total_found': 2, 'synced': 1, 'failed': 1}))
    app.dependency_overrides[chat.get_embedding_service] = lambda: service
    response = client.post('/api/chat/sync-embeddings')
    assert response.status_code == 200
    assert response.json()['data']['failed'] == 1
    assert client.post('/api/chat/sync-embeddings?batch_size=0').status_code == 422


def test_analysis_partial_failure_is_a_batch_result(client):
    thread_id = str(uuid4())
    service = SimpleNamespace(
        process_pending_threads=AsyncMock(return_value={
            'status': 'completed', 'total_threads': 2, 'rule_filtered': 1, 'llm_processed': 1,
            'total_api_calls': 1, 'succeeded': 1, 'failed': 1,
            'details': [{'thread_id': thread_id, 'status': 'failed', 'error_code': 'ANALYSIS_FAILED'}],
        }),
        analyze_thread=AsyncMock(return_value={'thread_id': thread_id, 'status': 'skipped', 'reason_code': 'NO_EMAILS_FOUND'}),
    )
    app.dependency_overrides[analysis.get_analysis_service] = lambda: service
    response = client.post('/api/analysis/process-pending')
    assert response.status_code == 200
    assert response.json()['data']['details'][0]['error_code'] == 'ANALYSIS_FAILED'
    response = client.post(f'/api/analysis/threads/{thread_id}')
    assert response.status_code == 200
    assert response.json()['data']['reason_code'] == 'NO_EMAILS_FOUND'
    assert client.post('/api/analysis/threads/invalid').status_code == 422
    assert client.post('/api/analysis/process-pending?limit=0').status_code == 422


def test_backfill_contract(client):
    service = SimpleNamespace(sync_history=AsyncMock(return_value={
        'status': 'success', 'owner_email': 'user@example.com', 'ingested_count': 0,
        'date_range': {'since': '2026-10-01T00:00:00Z', 'until': '2026-10-02T00:00:00Z'},
    }))
    app.dependency_overrides[sync.get_ingestion_service] = lambda: service
    response = client.post('/api/sync/backfill', json={'days_back': 1})
    assert response.status_code == 200
    assert response.json()['data']['ingested_count'] == 0
    assert client.post('/api/sync/backfill', json={'days_back': 0}).status_code == 422


def test_email_list_contract(client, monkeypatch):
    @asynccontextmanager
    async def session():
        yield object()
    email_id = str(uuid4())
    repository = SimpleNamespace(list_emails=AsyncMock(return_value=[{
        'id': email_id, 'provider_message_id': 'message-id', 'sender': 'user@example.com',
        'subject': 'Hello', 'date_sent': None, 'status': 'PENDING', 'private_column': 'SECRET',
    }]))
    monkeypatch.setattr(sync, 'async_session_factory', session)
    monkeypatch.setattr(sync, 'EmailRepository', lambda session: repository)
    response = client.get('/api/sync/emails')
    assert response.status_code == 200
    assert response.json()['data'][0]['id'] == email_id
    assert 'SECRET' not in response.text


def test_openapi_matches_runtime_contract():
    schema = app.openapi()
    for path, methods in schema['paths'].items():
        for method, operation in methods.items():
            responses = operation['responses']
            assert 'application/problem+json' in responses['422']['content']
            assert 'application/json' not in responses['422']['content']
            if path != '/api/auth/login':
                reference = responses['200']['content']['application/json']['schema']['$ref']
                model = schema['components']['schemas'][reference.rsplit('/', 1)[1]]
                assert set(model['properties']) == {'data', 'meta'}
            else:
                assert '307' in responses
                assert '200' not in responses

    def assert_references_resolve(value):
        if isinstance(value, dict):
            if '$ref' in value:
                target = schema
                for part in value['$ref'].removeprefix('#/').split('/'):
                    target = target[part]
            for child in value.values():
                assert_references_resolve(child)
        elif isinstance(value, list):
            for child in value:
                assert_references_resolve(child)
    assert_references_resolve(schema)
