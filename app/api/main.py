import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException

from app.api.readiness import build_status
from app.config.settings import Settings
from app.models.system import ErrorBody, ErrorResponse, SystemStatus
from app.services.errors import DomainError


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or Settings()
    from app.services.model_key import restore_key

    restore_key(configuration)

    @asynccontextmanager
    async def lifespan(application):
        application.state.retrieval = None
        if configuration.app_mode == "production":
            from app.retrieval.engine import Retrieval

            application.state.retrieval = await asyncio.to_thread(Retrieval, configuration)
        try:
            yield
        finally:
            if application.state.retrieval:
                application.state.retrieval.client.close()

    application = FastAPI(title="PinuiRAG", version="0.1.0", lifespan=lifespan)
    application.state.settings = configuration
    from app.api.product import router

    application.include_router(router)
    from app.api.administration import router as administration

    application.include_router(administration)
    from app.api.model_settings import router as model_settings

    application.include_router(model_settings)

    @application.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return error_response(request, exc.status, exc.code, exc.code)

    @application.exception_handler(TimeoutError)
    async def timeout_error(request: Request, exc: TimeoutError):
        return error_response(request, 504, "QUERY_TIMEOUT", "Query timed out")

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        if configuration.auth_mode == "local":
            from urllib.parse import urlsplit

            allowed = {"localhost", "127.0.0.1", "::1", "api"}
            if configuration.app_mode == "bootstrap":
                allowed.add("testserver")
            origin = request.headers.get("origin")
            if request.url.hostname not in allowed or (
                origin and urlsplit(origin).hostname not in allowed
            ):
                response = error_response(request, 403, "LOCAL_ACCESS_ONLY", "Local access only")
                response.headers["X-Request-ID"] = request.state.request_id
                return response
        try:
            response = await call_next(request)
        except Exception:
            # Do not log exception text: upstream errors may contain credentials.
            logger.error("Unhandled request failure request_id={}", request.state.request_id)
            response = error_response(request, 500, "INTERNAL_ERROR", "Internal server error")
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        return error_response(request, exc.status_code, code, "Request could not be completed")

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error_response(request, 422, "VALIDATION_ERROR", "Invalid request")

    @application.get("/health")
    async def health():
        return {
            "status": "alive",
            "stage": "local_retrieval" if configuration.app_mode == "production" else "T01",
        }

    @application.get(
        "/status", response_model=SystemStatus, responses={503: {"model": SystemStatus}}
    )
    async def status(request: Request):
        result = await build_status(configuration, request.state.request_id)
        return JSONResponse(
            status_code=200 if result.status == "ready" else 503,
            content=result.model_dump(),
        )

    return application


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message), request_id=request.state.request_id
    )
    return JSONResponse(status_code=status, content=body.model_dump())
