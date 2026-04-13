from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.api.analyze import router as analyze_router
from app.api.detections import router as detections_router
from app.api.documents import router as documents_router
from app.api.export import router as export_router
from app.api.page_reviews import router as page_reviews_router
from app.config import settings
from app.db.session import engine
from app.logging_config import configure_logging, get_logger
from app.middleware.request_id import RequestIdMiddleware
from app.models.schemas import Base
from app.security import (
    SecurityHeadersMiddleware,
    limiter,
    rate_limit_exceeded_handler,
)

configure_logging()
logger = get_logger(__name__)


async def _probe_llm_status() -> str:
    """Return one of: "ok", "unreachable", "disabled".

    The LLM layer is dormant by default (`settings.llm_tier2_enabled` and
    `settings.llm_tier3_enabled` both False). While dormant we report
    `"disabled"` without importing the provider at all — nothing in the
    live pipeline should touch Ollama. When an operator flips a flag for
    experimentation, this probe becomes a best-effort reachability check,
    bounded by the provider's own timeout.
    """
    if not (settings.llm_tier2_enabled or settings.llm_tier3_enabled):
        return "disabled"
    try:
        from app.llm import get_llm_provider

        provider = get_llm_provider()
        reachable = await provider.health_check()
        return "ok" if reachable else "unreachable"
    except Exception:
        logger.exception("llm.health_probe_raised")
        return "unreachable"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Create database tables (dev convenience — use Alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight, idempotent schema patch for columns that post-date the
        # original create_all. Alembic lives in the tree but isn't wired to a
        # version chain yet; until it is, new nullable columns get an
        # `IF NOT EXISTS` ALTER here so a running dev/pilot database picks
        # them up on the next restart without a manual migration.
        from sqlalchemy import text

        await conn.execute(
            text("ALTER TABLE detections ADD COLUMN IF NOT EXISTS original_bounding_boxes JSONB")
        )
    logger.info("db.tables_ensured")

    # Pre-initialize Deduce NER (~2s load time). Non-fatal — if this fails the
    # NER engine will lazily initialize on first use.
    try:
        from app.services.ner_engine import init_deduce

        init_deduce()
        logger.info("ner.deduce_initialized")
    except Exception:
        logger.warning("ner.deduce_init_failed", reason="will_lazy_init")

    # Advisory LLM reachability probe. Never fatal; the LLM layer is dormant
    # by default, in which case the probe short-circuits to "disabled" without
    # importing the provider. A warning is only logged when an operator has
    # flipped a flag on and the provider is actually unreachable.
    llm_status = await _probe_llm_status()
    if llm_status == "unreachable":
        logger.warning(
            "llm.unreachable_at_startup",
            provider=settings.llm_provider,
        )
    else:
        logger.info("llm.status", status=llm_status)

    yield

    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="WOO Buddy API",
        description="API for Dutch Woo document redaction",
        version="0.0.1",
        lifespan=lifespan,
    )

    # Wire slowapi rate limiting. `limiter` is attached to app state so the
    # `@limiter.limit(...)` decorator on individual routes can resolve it.
    app.state.limiter = limiter
    # Starlette types the handler as `(Request, Exception)`, but slowapi
    # always hands us a `RateLimitExceeded` — the cast keeps mypy quiet
    # without weakening runtime behavior.
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # NOTE on middleware order: Starlette's `add_middleware` prepends to the
    # stack, so the LAST-added middleware is the OUTERMOST wrapper. We want
    # RequestIdMiddleware to be outermost so that `request_id` is bound
    # before any other code runs — add it last.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.include_router(analyze_router)
    app.include_router(documents_router)
    app.include_router(detections_router)
    app.include_router(export_router)
    app.include_router(page_reviews_router)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Advisory health endpoint.

        Always returns 200. The `llm` field reports "disabled" while the
        LLM layer is dormant (the default), and reachability when an
        operator has flipped `llm_tier2_enabled`/`llm_tier3_enabled` on
        for experimentation. The legacy `ollama` field is kept as an
        alias so existing frontend banners don't break.
        """
        llm_status = await _probe_llm_status()
        return {"status": "ok", "llm": llm_status, "ollama": llm_status}

    return app


app = create_app()
