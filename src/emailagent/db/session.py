import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.emailagent.config import settings

logger = logging.getLogger("emailagent.db")

# Khởi tạo engine kết nối async với PostgreSQL
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,  # Tự động ping để kiểm tra kết nối còn sống không
)

# Factory tạo phiên làm việc (Session) bất đồng bộ
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)


# Dependency cấp phát session cho FastAPI hoặc service
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception as exc:
            logger.error("Database session error: %s", exc)
            await session.rollback()
            raise