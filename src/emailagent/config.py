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
    GMAIL_CREDENTIALS_PATH: str = "credentials.json"
    GMAIL_TOKEN_PATH: str = "token.json"

    # Cấu hình AI & LLM Gateway
    LLM_PROVIDER: str = "gemini"  # 'gemini' hoặc 'openai'
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLM_MODEL_NAME: str = "gemini-3.8-flash"
    VECTOR_DIMENSION: int = 768

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    DEFAULT_BACKFILL_DAYS: int = Field(30, description="Default days for history")
    MAX_BACKFILL_DAYS: int = Field(180, description="Max backfill days")
    FALLBACK_OWNER_EMAIL: str = Field("use@example.com", description="Email address for fallback owner")
    FALLBACK_OWNER_NAME: str = Field("Default user", description="Name for fallback owner")

    # --- Vector Memory & Embedding Configuration ---
    # --- Cấu hình Vector Memory & Embedding ---
    EMBEDDING_PROVIDER: str = Field("gemini", description="Embedding provider: 'gemini' | 'openai'")
    EMBEDDING_MODEL_NAME: str = Field("text-embedding-004", description="Google text embedding model name")
    VECTOR_DIMENSION: int = Field(768, description="Vector dimension matching database schema")

    # --- Cấu hình RAG / Trợ lý Chat ---
    RAG_TOP_K: int = Field(5, description="Number of candidate threads to retrieve")
    RAG_SIMILARITY_THRESHOLD: float = Field(0.60, description="Minimum cosine similarity threshold (0.0 to 1.0)")


# Singleton instance để import dùng chung toàn dự án
settings = Settings()
