"""Transport-independent application errors. Public messages live in locale catalogs."""
from enum import Enum


class ErrorCode(str, Enum):
    def __str__(self) -> str:
        return self.value

    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_NOT_CONFIGURED = "AUTH_NOT_CONFIGURED"
    AUTH_MISSING_CODE = "AUTH_MISSING_CODE"
    AUTH_INVALID_STATE = "AUTH_INVALID_STATE"
    AUTH_DENIED = "AUTH_DENIED"
    AUTH_SCOPE_REQUIRED = "AUTH_SCOPE_REQUIRED"
    AUTH_EXCHANGE_FAILED = "AUTH_EXCHANGE_FAILED"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"


class AppError(Exception):
    def __init__(self, code: ErrorCode):
        self.code = code
        super().__init__(code.value)
