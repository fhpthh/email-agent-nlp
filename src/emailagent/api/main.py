import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from src.emailagent.api.exception_handlers import register_exception_handlers
from src.emailagent.api.request_context import RequestContextMiddleware, RequestIdFilter
from src.emailagent.api.schemas.common import HealthData, SuccessResponse, success
from src.emailagent.api.schemas.problem import PROBLEM_RESPONSES

from src.emailagent.api.routers import analysis, chat, auth
from src.emailagent.api.routers import sync
from src.emailagent.config import settings
from src.emailagent.prompts.loader import prompt_loader
from src.emailagent.services.scheduler import AgentSchedulerRunner

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s request_id=%(request_id)s: %(message)s"
)
for handler in logging.getLogger().handlers:
    handler.addFilter(RequestIdFilter())
logger = logging.getLogger("emailagent")

scheduler_runner = AgentSchedulerRunner()


# Quản lý vòng đời khởi động và tắt ứng dụng
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up: %s (ENV=%s)", settings.APP_NAME, settings.ENV)

    prompt_loader.validate_all()

    if settings.SCHEDULER_ENABLED:
        scheduler_runner.start()
    else:
        logger.info("Background scheduler is disabled via configuration.")
    yield
    if scheduler_runner.is_running:
        scheduler_runner.shutdown(wait=False)
    logger.info("Application shutting down gracefully.")


# Khởi tạo instance FastAPI
app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Intelligent Email Brief & Reasoning Agent API",
    lifespan=lifespan,
    responses=PROBLEM_RESPONSES
)


app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)


# Endpoint kiểm tra trạng thái hoạt động của server
@app.get("/health", tags=["System"], response_model=SuccessResponse[HealthData], summary="Check application health")
async def health_check(request: Request):
    logger.debug("Health check ping received.")
    return success(request, HealthData(
        app_name=settings.APP_NAME, environment=settings.ENV,
        scheduler_running=scheduler_runner.is_running,
    ))


app.include_router(auth.router)
app.include_router(sync.router)
app.include_router(analysis.router)
app.include_router(chat.router)
