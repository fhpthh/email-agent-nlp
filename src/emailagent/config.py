from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Quản lý cấu hình tập trung từ biến môi trường
class Settings(BaseSettings):
    # Cấu hình ứng dụng
    APP_NAME: str = "Email Brief Agent"
    ENV: str = "development"
    DEBUG: bool = True

    # Kết nối cơ sở dữ liệu PostgreSQL (Host port 5434)
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgrespassword@localhost:5434/email_agent_db"
    )
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Tham số xử lý và đồng bộ (chống hardcode)
    INGESTION_BATCH_SIZE: int = Field(50, description="Max emails per fetch batch")
    SYNC_OVERLAP_MINUTES: int = Field(10, description="Overlap window for safety")
    THREAD_DEBOUNCE_SECONDS: int = Field(180, description="Debounce delay before summarizing thread")
    DEFAULT_TIMEZONE: str = Field("Asia/Ho_Chi_Minh", description="Timezone for resolving dates")

    # Provider đang kích hoạt: 'fake' | 'gmail' | 'outlook'
    ACTIVE_EMAIL_PROVIDER: str = "fake"

    # Cấu hình AI & LLM Gateway
    LLM_PROVIDER: str = "gemini"  # 'gemini' hoặc 'openai'
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLM_MODEL_NAME: str = "gemini-2.0-flash"
    VECTOR_DIMENSION: int = 768

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Singleton instance để import dùng chung toàn dự án
settings = Settings()