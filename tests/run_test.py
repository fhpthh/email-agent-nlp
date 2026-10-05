import asyncio
import sys
from datetime import date
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from src.emailagent.config import settings
from src.emailagent.db.session import engine
from src.emailagent.domain.enums import EmailCategory, PriorityLevel
from src.emailagent.domain.models import ActionItemModel, ThreadInsightModel
from src.emailagent.api.main import app

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


def log_pass(name: str):
    print(f"[{GREEN}PASS{RESET}] {name}")


def log_fail(name: str, err: Exception):
    print(f"[{RED}FAIL{RESET}] {name}: {err}")


async def main():
    print("=" * 60)
    print("RUNNING BASE FRAMEWORK SANITY VERIFICATION")
    print("=" * 60)
    all_passed = True

    # 1. Config Test
    try:
        assert settings.APP_NAME == "Email Brief Agent"
        assert "postgresql+asyncpg" in settings.DATABASE_URL
        log_pass("1. Configuration loaded from environment / .env")
    except Exception as e:
        log_fail("1. Configuration loaded", e)
        all_passed = False

    # 2. Database Connection Test
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1"))
            assert res.scalar() == 1
        log_pass("2. Async PostgreSQL Connection (asyncpg)")
    except Exception as e:
        log_fail("2. Async PostgreSQL Connection", e)
        all_passed = False

    # 3. Database Schema & Tables Test
    try:
        expected = {"accounts", "threads", "emails", "action_items"}
        async with engine.connect() as conn:
            res = await conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            )
            existing = {row[0] for row in res.fetchall()}
            assert expected.issubset(existing), f"Missing: {expected - existing}"
        log_pass(f"3. Database Tables verified: {sorted(list(expected))}")
    except Exception as e:
        log_fail("3. Database Tables verified", e)
        all_passed = False

    # 4. Domain Models Test
    try:
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
            summary="Technical discussion on email agent.",
            action_items=[action]
        )
        assert insight.category == EmailCategory.WORK
        assert len(insight.action_items) == 1
        log_pass("4. Domain Pydantic Models Validation")
    except Exception as e:
        log_fail("4. Domain Pydantic Models Validation", e)
        all_passed = False

    # 5. FastAPI Health API Test
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"
        log_pass("5. FastAPI Endpoint /health response: HTTP 200 OK")
    except Exception as e:
        log_fail("5. FastAPI Endpoint /health", e)
        all_passed = False

    print("=" * 60)
    if all_passed:
        print(f"{GREEN}ALL 5 BASE CHECKS PASSED SUCCESSFULLY! Ready for Day 2.{RESET}")
        sys.exit(0)
    else:
        print(f"{RED}SOME CHECKS FAILED. Please review the errors above.{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
