import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.emailagent.api.routers import sync
from src.emailagent.config import settings

# Cấu hình log chuẩn tiếng Anh
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("emailagent")


# Quản lý vòng đời khởi động và tắt ứng dụng
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up: %s (ENV=%s)", settings.APP_NAME, settings.ENV)
    yield
    logger.info("Application shutting down gracefully.")


# Khởi tạo instance FastAPI
app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Intelligent Email Brief & Reasoning Agent API",
    lifespan=lifespan
)


# Endpoint kiểm tra trạng thái hoạt động của server
@app.get("/health", tags=["System"])
async def health_check():
    logger.debug("Health check ping received.")
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.ENV
    }


app.include_router(sync.router)
