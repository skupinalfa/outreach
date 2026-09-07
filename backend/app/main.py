from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api import auth as auth_api
from app.api import contacts as contacts_api
from app.api import dashboard as dashboard_api
from app.api import drafts as drafts_api
from app.api import hunter as hunter_api
from app.api import organisations as organisations_api
from app.api import prompts as prompts_api
from app.api import settings as settings_api
from app.api import templates as templates_api
from app.api import todos as todos_api
from app.bootstrap import bootstrap_all
from app.config import get_settings
from app.db import SessionLocal
from app.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    log = get_logger("app")
    log.info("app_starting")
    with SessionLocal() as db:
        bootstrap_all(db)
        db.commit()
    log.info("app_ready")
    yield
    log.info("app_stopping")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="ColdMail API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_req: Request, exc: HTTPException) -> JSONResponse:
        payload: dict[str, Any]
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            payload = exc.detail
        else:
            payload = {"error": {"code": _default_code(exc.status_code), "message": str(exc.detail)}}
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(ValidationError)
    async def validation_exception_handler(_req: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request body failed validation.",
                    "detail": {"errors": exc.errors()},
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        _req: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # FastAPI's own body-parsing errors — map to our error taxonomy so clients get
        # a consistent shape (contracts/api.md).
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request body failed validation.",
                    "detail": {"errors": exc.errors()},
                }
            },
        )

    @app.get(f"{settings.api_prefix}/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_api.router, prefix=settings.api_prefix)
    app.include_router(organisations_api.router, prefix=settings.api_prefix)
    app.include_router(contacts_api.router, prefix=settings.api_prefix)
    app.include_router(drafts_api.router, prefix=settings.api_prefix)
    app.include_router(todos_api.router, prefix=settings.api_prefix)
    app.include_router(templates_api.router, prefix=settings.api_prefix)
    app.include_router(prompts_api.router, prefix=settings.api_prefix)
    app.include_router(settings_api.router, prefix=settings.api_prefix)
    app.include_router(dashboard_api.router, prefix=settings.api_prefix)
    app.include_router(hunter_api.router, prefix=settings.api_prefix)

    return app


def _default_code(status_code: int) -> str:
    mapping = {
        400: "bad_request",
        401: "authentication_required",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        500: "internal_error",
        502: "upstream_error",
    }
    return mapping.get(status_code, "error")


app = create_app()
