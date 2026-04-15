from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    The detection pipeline is 100% rule-based (regex + Deduce NER +
    wordlists + structure heuristics). There is no LLM — no settings
    for it, no provider client in the tree. If you ever want to add a
    local LLM pass back, start from `docs/reference/llm-revival.md`.
    """

    # Database
    database_url: str = "postgresql+asyncpg://woobuddy:woobuddy@localhost:5432/woobuddy"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Shared secret required on every API call. The SvelteKit server proxy
    # attaches this header; browsers cannot forge it cross-origin. Leave empty
    # in local development if the frontend calls the backend directly.
    proxy_shared_secret: str = ""

    # Brevo (#45 — public lead capture). Contacts submitted through
    # `POST /api/leads` are pushed straight into Brevo list `brevo_list_id`.
    # Brevo is the system of record for the audience list; there is no
    # dual-write to Postgres and no CSV export endpoint. Leave the API key
    # empty in local development — the endpoint will then return a generic
    # 500 so the form shows a retry rather than silently dropping signups.
    brevo_api_key: str = ""
    brevo_list_id: int = 4

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
