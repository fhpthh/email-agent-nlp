import pytest
from datetime import date
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from src.emailagent.config import settings
from src.emailagent.db.session import engine
from src.emailagent.domain.enums import EmailCategory, PriorityLevel
from src.emailagent.domain.models import ActionItemModel, ThreadInsightModel
from src.emailagent.api.main import app


# 1. Kiểm tra cấu hình nạp thành công từ .env
def test_settings_loaded():
    assert settings.APP_NAME == "Email Brief Agent"
    assert "postgresql+asyncpg" in settings.DATABASE_URL
    assert settings.ACTIVE_EMAIL_PROVIDER in ["fake", "gmail", "outlook"]


# 2. Kiểm tra kết nối bất đồng bộ tới PostgreSQL
@pytest.mark.asyncio
async def test_database_connection():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


# 3. Kiểm tra các bảng nghiệp vụ đã tồn tại trong database
@pytest.mark.asyncio
async def test_database_tables_exist():
    expected_tables = {"accounts", "threads", "emails", "action_items"}
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        existing_tables = {row[0] for row in result.fetchall()}
        assert expected_tables.issubset(existing_tables), f"Missing tables: {expected_tables - existing_tables}"


# 4. Kiểm tra Pydantic validation của Domain Models
def test_domain_models_validation():
    action = ActionItemModel(
        task="Finish architecture document",
        assignee="Developer",
        deadline=date(2026, 10, 6),
        priority=PriorityLevel.HIGH,
        evidence="Please finish the doc before 5PM today"
    )
    assert action.priority == PriorityLevel.HIGH

    insight = ThreadInsightModel(
        category=EmailCategory.WORK,
        is_urgent=True,
        needs_reply=False,
        summary="Discussion on technical architecture for Q4.",
        action_items=[action]
    )
    assert insight.category == EmailCategory.WORK
    assert len(insight.action_items) == 1


# 5. Kiểm tra FastAPI health check endpoint
@pytest.mark.asyncio
async def test_health_check_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["app_name"] == settings.APP_NAME
