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

    # Brevo (#45 — public lead capture). Every form submission fires a
    # transactional email to `brevo_notification_email` so the operator
    # actually reads the message. Newsletter subscription is a separate,
    # optional opt-in: when the submitter ticks the checkbox we also
    # push the contact into Brevo list `brevo_list_id`. Leave the API key
    # empty in local development — the endpoint will then return a generic
    # 500 so the form shows a retry rather than silently dropping signups.
    brevo_api_key: str = ""
    brevo_list_id: int = 4
    brevo_notification_email: str = "jaapstronks@gmail.com"
    brevo_sender_email: str = "noreply@woobuddy.nl"
    brevo_sender_name: str = "WOO Buddy"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
