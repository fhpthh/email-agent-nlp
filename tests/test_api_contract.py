"""Contract tests without database, scheduler, LLM, or external OAuth calls."""
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.testclient import TestClient

from src.emailagent.api.exception_handlers import register_exception_handlers
from src.emailagent.api.i18n import CATALOGS, resolve_locale
from src.emailagent.api.request_context import RequestContextMiddleware
from src.emailagent.api.schemas.common import SuccessResponse, success
from src.emailagent.api.schemas.problem import PROBLEM_RESPONSES
from src.emailagent.core.errors import AppError, ErrorCode


@pytest.fixture
def client():
    app = FastAPI(responses=PROBLEM_RESPONSES)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get('/ok', response_model=SuccessResponse[int])
    def ok(request: Request, count: int = Query(1, ge=1)):
        return success(request, count)

    @app.get('/app-error')
    def app_error():
        raise AppError(ErrorCode.AUTH_MISSING_CODE)

    @app.get('/unexpected')
    def unexpected():
        raise RuntimeError('SECRET_INTERNAL_PATH')

    @app.get('/http-error')
    def http_error():
        raise HTTPException(401, 'SECRET_INTERNAL_PATH', headers={'WWW-Authenticate': 'Bearer'})

    @app.get('/no-content', status_code=204)
    def no_content():
        return Response(status_code=204)

    @app.get('/bad-response', response_model=SuccessResponse[int])
    def bad_response(request: Request):
        return success(request, 'SECRET_INTERNAL_PATH')

    return TestClient(app, raise_server_exceptions=False)


def test_success_and_correlation(client):
    response = client.get('/ok', headers={'X-Request-ID': 'untrusted'})
    body = response.json()
    assert body['data'] == 1
    assert set(body) == {'data', 'meta'}
    assert body['meta']['request_id'] == response.headers['x-request-id']
    UUID(response.headers['x-request-id'])
    assert response.headers['x-request-id'] != 'untrusted'


@pytest.mark.parametrize('language,expected', [('en-US', 'Missing authorization code'), ('vi', 'Thiếu mã xác thực'), ('fr', 'Thiếu mã xác thực')])
def test_problem_details_and_translation(client, language, expected):
    response = client.get('/app-error', headers={'Accept-Language': language})
    body = response.json()
    assert response.status_code == body['status'] == 400
    assert response.headers['content-type'] == 'application/problem+json'
    assert body['title'] == expected
    assert body['code'] == 'AUTH_MISSING_CODE'
    assert body['type'].endswith('auth-missing-code')
    assert body['instance'] == f"urn:uuid:{body['request_id']}"
    assert body['request_id'] == response.headers['x-request-id']
    assert 'Accept-Language' in response.headers['vary']


@pytest.mark.parametrize('header,expected', [
    ('vi;q=0.2,en-US;q=0.9', 'en'), ('en;q=0,vi;q=1', 'vi'),
    ('en;q=garbage', 'vi'), ('en;q=2', 'vi'), ('en;q=nan', 'vi'), ('', 'vi'),
])
def test_language_negotiation(header, expected):
    assert resolve_locale(header) == expected


def test_catalogs_have_matching_keys():
    assert CATALOGS['en'].keys() == CATALOGS['vi'].keys()
    for code in ErrorCode:
        assert code.value in CATALOGS['en']


def test_validation_is_safe_and_localized(client):
    response = client.get('/ok?count=SECRET_INTERNAL_PATH', headers={'Accept-Language': 'en'})
    body = response.json()
    assert response.status_code == 422
    assert body['errors'][0]['location'] == ['query', 'count']
    assert body['errors'][0]['code'] == 'int_parsing'
    assert body['errors'][0]['detail'] == 'This field has an invalid value.'
    assert 'SECRET_INTERNAL_PATH' not in response.text


@pytest.mark.parametrize('path', ['/unexpected', '/bad-response'])
def test_internal_errors_are_safe(client, path):
    response = client.get(path)
    assert response.status_code == 500
    assert response.json()['code'] == 'INTERNAL_ERROR'
    assert 'SECRET_INTERNAL_PATH' not in response.text
    assert response.headers['x-request-id'] == response.json()['request_id']


def test_http_errors_preserve_headers(client):
    response = client.get('/http-error')
    assert response.status_code == 401
    assert response.headers['www-authenticate'] == 'Bearer'
    assert 'SECRET_INTERNAL_PATH' not in response.text
    assert response.json()['type'] == 'about:blank'
    assert client.get('/missing').json()['status'] == 404
    assert client.post('/ok').json()['status'] == 405


def test_no_content_is_not_wrapped(client):
    response = client.get('/no-content')
    assert response.status_code == 204
    assert response.content == b''


def test_concurrent_languages_are_isolated(client):
    def request(language):
        response = client.get('/app-error', headers={'Accept-Language': language})
        assert response.headers['content-language'] == language
        assert response.json()['title'] == CATALOGS[language]['AUTH_MISSING_CODE']['title']
        return response.headers['x-request-id']
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(request, ['en', 'vi'] * 5))
    assert len(set(ids)) == 10
