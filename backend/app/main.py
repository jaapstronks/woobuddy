from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.api.analyze import router as analyze_router
from app.api.detections import router as detections_router
from app.api.documents import router as documents_router
from app.api.export import router as export_router
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

# Tier 3 LLM content analysis is currently disabled in services/llm_engine.py.
# When re-enabled, flip this to True so the health endpoint probes the provider.
LLM_TIER_ENABLED = False


async def _probe_llm_status() -> str:
    """Return one of: "ok", "unreachable", "disabled".

    Probing is best-effort and bounded by the provider's own timeout.
    """
    if not LLM_TIER_ENABLED:
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
    logger.info("db.tables_ensured")

    # Pre-initialize Deduce NER (~2s load time). Non-fatal — if this fails the
    # NER engine will lazily initialize on first use.
    try:
        from app.services.ner_engine import init_deduce

        init_deduce()
        logger.info("ner.deduce_initialized")
    except Exception:
        logger.warning("ner.deduce_init_failed", reason="will_lazy_init")

    # Advisory LLM reachability probe. Never fatal; Tier 3 is dormant today, but
    # we log a warning so operators notice when the provider is unreachable.
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

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Advisory health endpoint.

        Always returns 200 so load balancers don't flap when the LLM provider
        is down (the app keeps working on Tier 1/2 without it). The `ollama`
        field surfaces LLM reachability for the frontend banner.
        """
        llm_status = await _probe_llm_status()
        return {"status": "ok", "ollama": llm_status}

    return app


app = create_app()
