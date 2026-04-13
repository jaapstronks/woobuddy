from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM layer — DORMANT by default.
    #
    # The live detection pipeline is regex + Deduce NER + wordlists + structure
    # heuristics. No LLM is called in the default code path. The Ollama provider
    # in `app/llm/` is kept in-tree as a parked revival path — see
    # `app/llm/README.md` for the rationale and the knobs below for turning it
    # back on in a controlled environment (e.g. an experimentation branch).
    #
    # Flip `llm_tier2_enabled=True` to re-enable the person-role classification
    # pass in `services/llm_engine.py`. `llm_tier3_enabled` is reserved for the
    # content-analysis tier, which has no active caller today.
    llm_tier2_enabled: bool = False
    llm_tier3_enabled: bool = False

    # LLM provider: only local Ollama is supported when the layer is revived.
    # No third-party hosted providers — document text must never leave the
    # operator's infrastructure.
    llm_provider: str = "ollama"

    # Ollama (dormant — only consulted when an `llm_tier*_enabled` flag is set)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:26b"
    ollama_keep_alive: int = -1

    # Database
    database_url: str = "postgresql+asyncpg://woobuddy:woobuddy@localhost:5432/woobuddy"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Shared secret required on every API call. The SvelteKit server proxy
    # attaches this header; browsers cannot forge it cross-origin. Leave empty
    # in local development if the frontend calls the backend directly.
    proxy_shared_secret: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
