import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.detections import router as detections_router
from app.api.documents import router as documents_router
from app.api.dossiers import router as dossiers_router
from app.api.export import router as export_router
from app.api.officials import router as officials_router
from app.config import settings
from app.db.session import engine
from app.models.schemas import Base
from app.services.storage import storage

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Create database tables (dev convenience — use Alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")

    # Create MinIO bucket
    try:
        await storage.ensure_bucket()
        logger.info("MinIO bucket ensured")
    except Exception:
        logger.warning("Could not connect to MinIO — storage will fail until it's available")

    # Pre-initialize Deduce NER (~2s load time)
    try:
        from app.services.ner_engine import init_deduce

        init_deduce()
        logger.info("Deduce NER engine initialized")
    except Exception:
        logger.warning("Could not initialize Deduce — NER will initialize on first use")

    yield

    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="WOO Buddy API",
        description="API for Dutch Woo document redaction",
        version="0.0.1",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(dossiers_router)
    app.include_router(documents_router)
    app.include_router(detections_router)
    app.include_router(officials_router)
    app.include_router(export_router)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
