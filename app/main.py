"""FastAPI 앱. 라우터는 각 작업(T1-3, T1-4 등)에서 붙인다."""

from fastapi import FastAPI

from app.api.auth import warn_if_api_key_missing
from app.api.errors import register_error_handlers
from app.api.health import install_health
from app.config import Settings, get_settings
from app.logging import RequestLoggingMiddleware, configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    warn_if_api_key_missing(settings)

    app = FastAPI(title="어디갈래 AI 서버", version="0.1.0")
    app.state.settings = settings
    # 오류 미들웨어가 로깅 미들웨어 안쪽에 오도록 먼저 등록한다.
    register_error_handlers(app)
    app.add_middleware(RequestLoggingMiddleware)
    install_health(app)
    return app


app = create_app()
