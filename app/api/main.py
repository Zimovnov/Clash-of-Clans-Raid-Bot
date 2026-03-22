import logging

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_internal_api_token
from app.api.routes.internal import router as internal_router
from app.core.config import get_settings


logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ClashInfoBot API",
        version="0.1.0",
        docs_url="/docs" if settings.api_docs_enabled else None,
        redoc_url="/redoc" if settings.api_docs_enabled else None,
        openapi_url="/openapi.json" if settings.api_docs_enabled else None,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready(session: AsyncSession = Depends(get_db_session)) -> dict[str, str]:
        await session.execute(text("SELECT 1"))
        return {"status": "ready"}

    if settings.internal_api_token:
        app.include_router(internal_router, dependencies=[Depends(require_internal_api_token)])
    else:
        logger.warning("internal_api_disabled_missing_token")

    return app


app = create_app()
