from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM provider: "ollama" or "anthropic"
    llm_provider: str = "ollama"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:26b"
    ollama_keep_alive: int = -1

    # Anthropic (fallback)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"

    # Database
    database_url: str = "postgresql+asyncpg://woobuddy:woobuddy@localhost:5432/woobuddy"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "woobuddy"
    minio_secret_key: str = "woobuddy-secret"
    minio_bucket: str = "documents"
    minio_secure: bool = False

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
