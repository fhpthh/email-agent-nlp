from typing import Generic, TypeVar, Literal
from pydantic import BaseModel
from fastapi import Request

T = TypeVar("T")


class ResponseMeta(BaseModel):
    request_id: str


class SuccessResponse(BaseModel, Generic[T]):
    data: T
    meta: ResponseMeta


def success(request: Request, data: T) -> SuccessResponse[T]:
    return SuccessResponse(data=data, meta=ResponseMeta(request_id=request.state.request_id))


class HealthData(BaseModel):
    status: Literal["healthy"] = "healthy"
    app_name: str
    environment: str
    scheduler_running: bool
