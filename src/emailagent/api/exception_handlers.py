"""HTTP mapping and RFC 9457 rendering; never expose raw exception messages."""
import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from src.emailagent.api.i18n import translate
from src.emailagent.api.schemas.problem import ProblemDetails, ValidationIssue
from src.emailagent.core.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)
ERROR_STATUS = {
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.AUTH_NOT_CONFIGURED: 503,
    ErrorCode.AUTH_MISSING_CODE: 400,
    ErrorCode.AUTH_INVALID_STATE: 400,
    ErrorCode.AUTH_DENIED: 400,
    ErrorCode.AUTH_SCOPE_REQUIRED: 403,
    ErrorCode.AUTH_EXCHANGE_FAILED: 502,
    ErrorCode.AUTH_TOKEN_INVALID: 500,
    ErrorCode.ANALYSIS_FAILED: 500,
}


def problem_response(request: Request, status: int, code: str, *, errors=None, headers=None):
    locale = request.state.locale
    request_id = request.state.request_id
    problem = ProblemDetails(
        type=f"urn:emailagent:problem:{code.lower().replace('_', '-')}",
        title=translate(code, locale, "title"),
        status=status,
        detail=translate(code, locale),
        instance=f"urn:uuid:{request_id}",
        code=code,
        request_id=request_id,
        errors=errors,
    )
    # Generic HTTP exceptions use the standard HTTP problem type.
    if code.startswith("HTTP_"):
        problem.type = "about:blank"
        from src.emailagent.api.i18n import CATALOGS
        if code not in CATALOGS[locale]:
            try:
                problem.title = HTTPStatus(status).phrase
            except ValueError:
                problem.title = "HTTP error"
    response_headers = dict(headers or {})
    response_headers.update({"Content-Language": locale, "X-Request-ID": request_id, "Cache-Control": "no-store"})
    response_headers["Vary"] = ", ".join(filter(None, [response_headers.get("Vary"), "Accept-Language"]))
    return JSONResponse(
        problem.model_dump(mode="json", exclude_none=True), status_code=status,
        media_type="application/problem+json", headers=response_headers,
    )


async def app_error_handler(request: Request, exc: AppError):
    status = ERROR_STATUS[exc.code]
    if status >= 500:
        logger.error("Application error code=%s request_id=%s", exc.code, request.state.request_id, exc_info=exc)
    return problem_response(request, status, exc.code)


async def validation_error_handler(request: Request, exc: RequestValidationError):
    issues = [ValidationIssue(
        location=list(error["loc"]), code=error["type"],
        detail=translate("validation.required" if error["type"] == "missing" else "validation.invalid", request.state.locale),
    ) for error in exc.errors()]
    return problem_response(request, 422, ErrorCode.VALIDATION_ERROR, errors=issues)


async def http_error_handler(request: Request, exc: HTTPException):
    if exc.status_code >= 500:
        return problem_response(request, exc.status_code, ErrorCode.INTERNAL_ERROR, headers=exc.headers)
    return problem_response(request, exc.status_code, f"HTTP_{exc.status_code}", headers=exc.headers)


async def unexpected_error_handler(request: Request, exc: Exception):
    logger.error("Unhandled error request_id=%s", request.state.request_id, exc_info=exc)
    return problem_response(request, 500, ErrorCode.INTERNAL_ERROR)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
