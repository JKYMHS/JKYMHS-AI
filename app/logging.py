"""JSON 한 줄 구조화 로그와 요청 처리 시간 미들웨어 (TRD 10).

- 모든 로그에 `request_id`가 붙는다. 요청 처리 중 `bind_request_id()`로 정한다.
  Spring 요청의 `requestId`는 본문에 있으므로, 본문을 파싱한 쪽(라우터)이 호출한다.
- 요청 본문과 쿼리 문자열은 남기지 않는다. 출발지 좌표가 들어 있다 (TRD 8).
"""

import json
import logging
import sys
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# 요청마다 새 dict를 담는다. dict를 고쳐 쓰므로, 하위 코드가 복사된 컨텍스트에서
# 값을 정해도 미들웨어의 마지막 로그에 반영된다.
_log_context: ContextVar[dict[str, Any] | None] = ContextVar("log_context", default=None)

# LogRecord 기본 속성. 이것 외의 속성(`extra=`)은 JSON 필드로 옮긴다.
_RESERVED = frozenset(
    vars(logging.LogRecord("", logging.INFO, "", 0, "", None, None)).keys()
    | {"message", "asctime", "taskName", "color_message", "request_id"}
)


def bind_request_id(request_id: int | str | None) -> None:
    """현재 요청(또는 작업)의 로그에 `request_id`를 붙인다."""
    ctx = _log_context.get()
    if ctx is None:
        _log_context.set({"request_id": request_id})
    else:
        ctx["request_id"] = request_id


def get_request_id() -> int | str | None:
    ctx = _log_context.get()
    return None if ctx is None else ctx.get("request_id")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_base_record_factory = logging.getLogRecordFactory()


def _record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    # 로그를 남기는 시점의 request_id를 레코드에 담는다(포맷 시점이 아니라).
    record = _base_record_factory(*args, **kwargs)
    record.request_id = get_request_id()
    return record


class _JsonHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """`configure_logging`이 붙인 핸들러. 여러 번 불러도 하나만 남긴다."""


def configure_logging(level: str = "INFO") -> None:
    """루트 로거와 uvicorn 로거를 JSON 한 줄 형식으로 맞춘다."""
    handler = _JsonHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    for old in [h for h in root.handlers if isinstance(h, _JsonHandler)]:
        root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(level.upper())
    logging.setLogRecordFactory(_record_factory)

    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    # uvicorn 접근 로그는 쿼리 문자열·클라이언트 주소를 남기므로 끄고 아래 미들웨어로 대신한다.
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False


access_logger = logging.getLogger("app.access")


class RequestLoggingMiddleware:
    """요청마다 메서드·경로·상태·처리 시간을 한 줄 남긴다. 본문은 읽지 않는다."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = _log_context.set({"request_id": None})
        start = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            access_logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
            _log_context.reset(token)
