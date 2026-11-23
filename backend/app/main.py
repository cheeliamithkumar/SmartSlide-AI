"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings
from app.database import init_db
from app.routes import documents, health, jobs, presentations
from app.services.cleanup import CleanupThread, cleanup_expired

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("smartslide")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    init_db()
    try:
        cleanup_expired()
    except Exception:  # pragma: no cover
        logger.exception("Initial cleanup failed")
    cleaner = None
    if settings.environment != "test":
        cleaner = CleanupThread()
        cleaner.start()
    logger.info("SmartSlide AI started (AI provider: %s)", settings.ai_provider)
    yield
    if cleaner:
        cleaner.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="SmartSlide AI API",
        version=__version__,
        description="Convert educational PDFs into editable Summary and Detailed PowerPoint presentations.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        errors = [
            {"field": ".".join(str(x) for x in e.get("loc", [])[1:]), "message": e.get("msg", "Invalid value")}
            for e in exc.errors()
        ]
        first = errors[0]["message"] if errors else "Invalid request"
        return JSONResponse(status_code=422, content={"detail": first, "errors": errors})

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # pragma: no cover
        logger.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    for r in (health.router, documents.router, jobs.router, presentations.router):
        app.include_router(r)
    return app


app = create_app()
