"""FastAPI 앱. 라우터는 각 작업(T1-3, T1-4 등)에서 붙인다."""

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.logging import RequestLoggingMiddleware, configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="어디갈래 AI 서버", version="0.1.0")
    app.state.settings = settings
    app.add_middleware(RequestLoggingMiddleware)
    return app


app = create_app()
