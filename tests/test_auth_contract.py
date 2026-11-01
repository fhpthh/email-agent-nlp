from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.emailagent.api.exception_handlers import register_exception_handlers
from src.emailagent.api.request_context import RequestContextMiddleware
from src.emailagent.api.routers import auth
from src.emailagent.api.schemas.problem import PROBLEM_RESPONSES
from src.emailagent.core.errors import AppError, ErrorCode
from src.emailagent.services import auth as auth_module


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_module.settings, 'GMAIL_TOKEN_PATH', str(tmp_path / 'token.json'))
    return auth_module.GmailAuthService(auth_module.OAuthSessionStore())


@pytest.fixture
def client(service):
    app = FastAPI(responses=PROBLEM_RESPONSES)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(auth.router)
    app.dependency_overrides[auth_module.get_auth_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


def seed(client, service):
    service.sessions.put('test-state', 'test-verifier')
    client.cookies.set(auth.STATE_COOKIE, 'test-state')


def test_status_without_token_has_stable_shape(client):
    response = client.get('/api/auth/status')
    assert response.status_code == 200
    assert response.json()['data'] == {
        'authenticated': False, 'state': 'not_connected', 'expired': False,
        'has_refresh_token': False, 'expiry': None,
    }


def test_invalid_token_is_problem_not_success(client, service):
    from pathlib import Path
    Path(auth_module.settings.GMAIL_TOKEN_PATH).write_text('not json SECRET')
    response = client.get('/api/auth/status')
    assert response.status_code == 500
    assert response.json()['code'] == 'AUTH_TOKEN_INVALID'
    assert 'SECRET' not in response.text
    assert 'token.json' not in response.text


def test_expired_token_with_refresh_is_distinguished(client, service, monkeypatch):
    monkeypatch.setattr(service, 'credentials', lambda: SimpleNamespace(valid=False, expired=True, refresh_token='secret', expiry=None))
    data = client.get('/api/auth/status').json()['data']
    assert data['state'] == 'expired'
    assert data['has_refresh_token'] is True
    assert data['authenticated'] is False


def test_login_remains_redirect_with_cookie(client, service, monkeypatch):
    monkeypatch.setattr(service, 'login', lambda: ('https://accounts.google.com/example', 'test-state'))
    response = client.get('/api/auth/login', follow_redirects=False)
    assert response.status_code == 307
    assert response.headers['location'] == 'https://accounts.google.com/example'
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=lax' in response.headers['set-cookie']
    assert response.content == b''


@pytest.mark.parametrize('query,expected', [('', 'AUTH_INVALID_STATE'), ('?state=unknown&code=x', 'AUTH_INVALID_STATE')])
def test_callback_rejects_invalid_state(client, query, expected):
    response = client.get('/api/auth/callback' + query)
    assert response.status_code == 400
    assert response.json()['code'] == expected


@pytest.mark.parametrize('query,expected', [('?state=test-state', 'AUTH_MISSING_CODE'), ('?state=test-state&error=SECRET', 'AUTH_DENIED')])
def test_callback_missing_code_or_denied(client, service, query, expected):
    seed(client, service)
    response = client.get('/api/auth/callback' + query)
    assert response.json()['code'] == expected
    assert 'SECRET' not in response.text


def test_sessions_are_bound_expiring_and_single_use(service, monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(auth_module, 'monotonic', lambda: clock[0])
    service.sessions.put('state', 'verifier')
    with pytest.raises(AppError):
        service.sessions.consume('state', 'other-browser')
    assert service.sessions.consume('state', 'state').verifier == 'verifier'
    with pytest.raises(AppError):
        service.sessions.consume('state', 'state')
    service.sessions.put('state', 'verifier')
    clock[0] += auth_module.SESSION_TTL_SECONDS + 1
    with pytest.raises(AppError):
        service.sessions.consume('state', 'state')


def mock_flow(service, monkeypatch, scopes):
    creds = SimpleNamespace(granted_scopes=scopes, scopes=auth_module.SCOPES, to_json=lambda: '{"token":"secret"}')
    flow = Mock(credentials=creds)
    monkeypatch.setattr(service, '_flow', lambda state=None: flow)
    return flow


def test_callback_checks_exact_granted_scope(client, service, monkeypatch):
    seed(client, service)
    mock_flow(service, monkeypatch, ['https://www.googleapis.com/auth/gmail.send'])
    response = client.get('/api/auth/callback?state=test-state&code=x')
    assert response.status_code == 403
    assert response.json()['code'] == 'AUTH_SCOPE_REQUIRED'


def test_callback_success_saves_token_without_exposing_path(client, service, monkeypatch):
    from pathlib import Path
    seed(client, service)
    flow = mock_flow(service, monkeypatch, auth_module.SCOPES)
    gmail = Mock()
    gmail.users.return_value.getProfile.return_value.execute.return_value = {'emailAddress': 'user@example.com'}
    monkeypatch.setattr(auth_module, 'build', lambda *args, **kwargs: gmail)
    response = client.get('/api/auth/callback?state=test-state&code=x')
    assert response.status_code == 200
    assert response.json()['data'] == {'connected_email': 'user@example.com'}
    assert 'token_saved_to' not in response.text
    assert flow.code_verifier == 'test-verifier'
    token = Path(auth_module.settings.GMAIL_TOKEN_PATH)
    assert token.read_text() == '{"token":"secret"}'
    assert token.stat().st_mode & 0o777 == 0o600
    assert client.get('/api/auth/callback?state=test-state&code=x').status_code == 400


def test_unconfigured_auth_does_not_expose_path(client, monkeypatch, tmp_path):
    monkeypatch.setattr(auth_module.settings, 'GMAIL_CREDENTIALS_PATH', str(tmp_path / 'private-missing.json'))
    response = client.get('/api/auth/login')
    assert response.status_code == 503
    assert response.json()['code'] == 'AUTH_NOT_CONFIGURED'
    assert 'private-missing' not in response.text


def test_exchange_failure_is_safe(client, service, monkeypatch):
    seed(client, service)
    flow = mock_flow(service, monkeypatch, auth_module.SCOPES)
    flow.fetch_token.side_effect = auth_module.OAuth2Error(description='SECRET')
    response = client.get('/api/auth/callback?state=test-state&code=x')
    assert response.status_code == 502
    assert response.json()['code'] == 'AUTH_EXCHANGE_FAILED'
    assert 'SECRET' not in response.text
