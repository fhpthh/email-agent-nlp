from pathlib import Path
import pytest
from sqlalchemy import text

from src.emailagent.adapters.provider.fake import FakeEmailProvider
from src.emailagent.db.session import async_session_factory
from src.emailagent.services.ingestion import IngestionService


@pytest.mark.asyncio
async def test_fake_ingestion_service_flow():
    """Kiểm tra luồng đồng bộ email từ Fake Provider vào Database."""
    mock_file = Path("tests/data/mock_emails.json")
    assert mock_file.exists(), "File mock emails không tồn tại!"

    # 1. Khởi tạo Service với Fake Provider
    provider = FakeEmailProvider(mock_file_path=mock_file)
    service = IngestionService(provider=provider, session_factory=async_session_factory)

    # 2. Chạy sync history 30 ngày
    result = await service.sync_history(days_back=30)

    # 3. Assert kết quả trả về
    assert result["status"] == "success"
    assert result["ingested_count"] > 0
    assert result["owner_email"] is not None

    # 4. Kiểm tra dữ liệu đã thực sự được ghi vào PostgreSQL
    async with async_session_factory() as session:
        count_emails = await session.execute(text("SELECT COUNT(*) FROM emails;"))
        assert count_emails.scalar() >= result["ingested_count"]

        count_threads = await session.execute(text("SELECT COUNT(*) FROM threads;"))
        assert count_threads.scalar() > 0