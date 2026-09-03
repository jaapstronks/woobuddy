from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    The detection pipeline is 100% rule-based (regex + Deduce NER +
    wordlists + structure heuristics). There is no LLM — no settings
    for it, no provider client in the tree. If you ever want to add a
    local LLM pass back, start from `docs/reference/llm-revival.md`.
    """

    # Deployment environment. "development" (the default) keeps optional
    # integrations quiet when they are unconfigured; anything else means a
    # real deployment, where a missing mail key is a misconfiguration worth
    # shouting about at startup. Set ENVIRONMENT=production on the VPS.
    environment: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://woobuddy:woobuddy@localhost:5432/woobuddy"

    # CORS — 5173 is the canonical Vite dev port; 5174 is Vite's auto-fallback
    # when 5173 is already taken (a leftover dev server, another project on
    # the same machine, etc.). Adding the fallback here saves a confusing
    # round of "why is CORS blocking me?" the first time it shifts.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
    ]

    # Shared secret required on every API call. The SvelteKit server proxy
    # attaches this header; browsers cannot forge it cross-origin. Leave empty
    # in local development if the frontend calls the backend directly.
    proxy_shared_secret: str = ""

    # Lead capture (public contact form). Every submission fires a
    # transactional email to `notification_email` via Scaleway TEM so the
    # operator reads the message. Newsletter subscription is a separate,
    # optional opt-in: when the submitter ticks the checkbox we also
    # subscribe the contact to the Listmonk list `listmonk_list_uuid`.

    # Scaleway TEM (transactional email). Auth is the Scaleway secret key
    # (sent as `X-Auth-Token`); `scaleway_project_id` scopes the send. The
    # From-address must sit on a verified TEM sending domain. The hosted
    # tier sends as `hallo@woobuddy.nl` (#74): the sender domain is part of
    # the trust story the landing page sells, and the address is a real
    # forwarding alias, so replying to a WOO Buddy mail reaches a human.
    # Self-hosters point `tem_from_email` at their own verified domain.
    # Leave `scaleway_secret_key` empty in local dev — the endpoint then
    # returns a generic 500 so the form shows a retry rather than silently
    # dropping signups.
    scaleway_secret_key: str = ""
    scaleway_project_id: str = ""
    scaleway_tem_region: str = "fr-par"
    tem_from_email: str = "hallo@woobuddy.nl"
    tem_from_name: str = "WOO Buddy"
    notification_email: str = "jaap@jaapstronks.nl"

    # Listmonk (self-hosted, EU) — the optional newsletter list. WOO Buddy
    # runs the double opt-in itself (#76) and writes to Listmonk through the
    # admin API only after the recipient confirmed, so an API user is needed
    # (Listmonk → Admin → Users → type API, with `lists:get` and
    # `subscribers:get`/`subscribers:manage`). Leave `listmonk_list_uuid`
    # empty — or the credentials empty — to disable the newsletter opt-in
    # entirely; the contact form keeps working either way.
    listmonk_url: str = "https://listmonk.dreamkit.eu"
    listmonk_list_uuid: str = ""
    listmonk_api_user: str = ""
    listmonk_api_token: str = ""

    # HMAC secret for the newsletter confirmation link (#76). Any long random
    # string; rotating it invalidates confirmation links that are still in
    # flight, which is a 48-hour window at most. Empty disables the opt-in
    # rather than minting forgeable tokens.
    leads_confirm_secret: str = ""

    # Where the confirmation link points. The mail is sent by the backend but
    # the link must land on the site the visitor recognises, so this is the
    # public origin of the frontend, not the API.
    public_site_url: str = "https://woobuddy.nl"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
