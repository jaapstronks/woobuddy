from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.api.analyze import router as analyze_router
from app.api.custom_terms import router as custom_terms_router
from app.api.detections import router as detections_router
from app.api.documents import router as documents_router
from app.api.export import router as export_router
from app.api.leads import router as leads_router
from app.api.page_reviews import router as page_reviews_router
from app.api.reference_names import router as reference_names_router
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
        # #15 — Tier 2 role classification. Nullable, no default: pre-existing
        # rows stay NULL and the UI shows the three chips until a reviewer
        # picks one.
        await conn.execute(
            text("ALTER TABLE detections ADD COLUMN IF NOT EXISTS subject_role VARCHAR(30)")
        )
        # #18 — split and merge audit columns. `split_from` points at the
        # original row; it uses SET NULL on delete (defined via the
        # SQLAlchemy FK) so surviving halves outlive the original. The FK
        # itself is added here for fresh environments; in running dev/pilot
        # databases the column is added plain and the constraint is
        # attached separately so the whole block stays idempotent.
        await conn.execute(text("ALTER TABLE detections ADD COLUMN IF NOT EXISTS split_from UUID"))
        await conn.execute(
            text("ALTER TABLE detections ADD COLUMN IF NOT EXISTS merged_from JSONB")
        )
        # #20 — character offsets into the server-joined full text, captured
        # at analyze time so the frontend can match detections to structure
        # spans on reload without re-running analyze. Nullable; pre-existing
        # rows stay NULL.
        await conn.execute(
            text("ALTER TABLE detections ADD COLUMN IF NOT EXISTS start_char INTEGER")
        )
        await conn.execute(text("ALTER TABLE detections ADD COLUMN IF NOT EXISTS end_char INTEGER"))
        # Environmental-information flag. NOT NULL with a server default so
        # pre-existing rows backfill to `false` without a separate UPDATE.
        await conn.execute(
            text(
                "ALTER TABLE detections ADD COLUMN IF NOT EXISTS "
                "is_environmental BOOLEAN NOT NULL DEFAULT FALSE"
            )
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

    # Load the Meertens voornamen + CBS achternamen name lists once and
    # cache them on app.state so tests / diagnostics can introspect the
    # loaded set sizes. The name engine ALSO keeps its own module-level
    # cache so callers don't have to thread `app.state` through every
    # analyze request. Non-fatal: missing files fall back to empty sets
    # and the pipeline continues on the heuristic-only verdict.
    try:
        from app.services.ner_engine import init_name_lists

        app.state.name_lists = init_name_lists()
        logger.info(
            "ner.name_lists_initialized",
            first_names=len(app.state.name_lists.first_names),
            last_names=len(app.state.name_lists.last_names),
        )
    except Exception:
        logger.warning("ner.name_lists_init_failed", reason="will_lazy_init")

    # Load the function-title lists for the rule-based role classifier
    # (#13). Cached on app.state for diagnostics; the role_engine module
    # ALSO keeps a process-level cache so callers don't have to thread
    # app.state through every request. Missing files fall back to empty
    # lists — the pipeline will then behave as if no titles were found.
    try:
        from app.services.role_engine import init_function_title_lists

        app.state.function_title_lists = init_function_title_lists()
        logger.info(
            "role_engine.lists_initialized",
            publiek=len(app.state.function_title_lists.publiek),
            ambtenaar=len(app.state.function_title_lists.ambtenaar),
        )
    except Exception:
        logger.warning("role_engine.lists_init_failed", reason="will_lazy_init")

    # Load the gemeente-whitelist index (#49) — 342 municipalities + their
    # public addresses/contact data + ~14k named public officials
    # (raadsleden, burgemeesters, wethouders, Woo-contactpersonen). Used
    # by the pipeline to suppress false positives on public municipal
    # data. Cached on app.state for diagnostics; the whitelist_engine
    # module also keeps its own process-level cache. Missing CSV files
    # degrade to an empty index — the pipeline keeps working.
    try:
        from app.services.whitelist_engine import init_whitelist_index

        app.state.whitelist_index = init_whitelist_index()
        logger.info(
            "whitelist_engine.initialized",
            municipalities=len(app.state.whitelist_index.municipalities),
            officials=sum(len(v) for v in app.state.whitelist_index.officials_by_gm.values()),
        )
    except Exception:
        logger.warning("whitelist_engine.init_failed", reason="will_lazy_init")

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
    app.include_router(reference_names_router)
    app.include_router(custom_terms_router)
    app.include_router(leads_router)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Advisory health endpoint. Always returns 200."""
        return {"status": "ok"}

    return app


app = create_app()
