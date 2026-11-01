from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    location: list[str | int]
    code: str
    detail: str


class ProblemDetails(BaseModel):
    type: str
    title: str
    status: int = Field(ge=400, le=599)
    detail: str
    instance: str
    code: str
    request_id: str
    errors: list[ValidationIssue] | None = None


# Inline the nested issue schema so references remain valid when embedded in OpenAPI.
_problem_schema = ProblemDetails.model_json_schema()
_problem_schema["properties"]["errors"]["anyOf"][0]["items"] = _problem_schema.pop("$defs")["ValidationIssue"]

PROBLEM_RESPONSES = {
    status: {
        "description": description,
        "content": {"application/problem+json": {"schema": _problem_schema}},
    }
    for status, description in {
        400: "Invalid request", 401: "Authentication required", 403: "Permission denied",
        404: "Resource not found", 405: "Method not allowed", 422: "Validation failed",
        500: "Internal error", 502: "Upstream service failed", 503: "Service unavailable",
    }.items()
}
