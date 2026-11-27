"""오류 응답 형식과 예외 처리기 (TRD 6).

모든 오류는 `{"code": "...", "message": "..."}` 형식으로 돌려준다.
오류 본문에는 내부 정보(스택, 예외 내용)와 요청 값을 넣지 않는다.
요청에 출발지 좌표가 들어 있기 때문이다 (TRD 8).
"""

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

# 422 메시지에 적을 필드 수. 나머지는 개수만 적는다.
_MAX_FIELDS_IN_MESSAGE = 5

_HTTP_CODES = {
    401: "UNAUTHORIZED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
}


class ErrorBody(BaseModel):
    code: str
    message: str


class ApiError(Exception):
    """앱 코드가 정해진 상태·코드로 응답할 때 던지는 예외."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers


def error_response(
    status: int, code: str, message: str, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    body = ErrorBody(code=code, message=message)
    return JSONResponse(status_code=status, content=body.model_dump(), headers=headers)


def not_found() -> ApiError:
    """없는 경로와 같은 404. 경로가 있다는 사실을 드러내지 않을 때 쓴다."""
    return ApiError(404, "NOT_FOUND", "Not Found")


async def _handle_api_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return error_response(exc.status, exc.code, exc.message, exc.headers)


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    # 없는 경로(404), 허용하지 않는 메서드(405) 등 Starlette가 만든 오류.
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")
    return error_response(exc.status_code, code, str(exc.detail), exc.headers)


def _field_path(error: dict[str, Any]) -> str:
    return ".".join(str(part) for part in error.get("loc", ()))


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    # 어느 필드가 어떤 종류로 틀렸는지만 적는다. `input`·`msg`에는 요청 값이 들어갈 수 있다.
    assert isinstance(exc, RequestValidationError)
    errors = list(exc.errors())
    fields = [f"{_field_path(e)}({e.get('type', 'invalid')})" for e in errors]
    shown = ", ".join(fields[:_MAX_FIELDS_IN_MESSAGE])
    if len(fields) > _MAX_FIELDS_IN_MESSAGE:
        shown += f" 외 {len(fields) - _MAX_FIELDS_IN_MESSAGE}건"
    logger.warning("invalid request", extra={"fields": fields})
    return error_response(422, "INVALID_REQUEST", f"요청 형식 오류: {shown}")


class UnhandledErrorMiddleware:
    """처리하지 않은 예외를 500 `INTERNAL`로 바꾼다.

    스택은 로그에만 남긴다. `RequestLoggingMiddleware` 안쪽에 두어야
    오류 로그에 `request_id`가 붙고 접근 로그에 500이 남는다.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception("unhandled error")
            if started:
                # 응답을 이미 보내기 시작했으면 바꿀 수 없다. 서버가 연결을 끊게 둔다.
                raise
            response = error_response(500, "INTERNAL", "Internal Server Error")
            await response(scope, receive, send)


def register_error_handlers(app: FastAPI) -> None:
    """오류 처리기를 등록한다.

    `UnhandledErrorMiddleware`가 `RequestLoggingMiddleware` 안쪽에 오도록,
    로깅 미들웨어를 붙이기 전에 부른다.
    """
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_middleware(UnhandledErrorMiddleware)
