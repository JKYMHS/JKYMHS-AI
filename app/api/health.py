"""`GET /health` (TRD 4). 인증 없음, 허용한 주소(기본 localhost)에서만 응답한다.

확인 항목은 등록식이다. 나중 작업이 `register_health_check(app, "db", check)`로 더한다.
항목 하나라도 거짓이거나 실패하면 `status`는 `degraded`다. 프로세스가 응답하므로 HTTP는 200.
"""

import asyncio
import ipaddress
import logging
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, FastAPI, Request
from pydantic import BaseModel

from app.api.errors import not_found
from app.config import Settings

logger = logging.getLogger(__name__)

HealthCheck = Callable[[Request], Awaitable[bool]]

# 항목 하나가 이보다 오래 걸리면 실패로 본다.
CHECK_TIMEOUT_SEC = 2.0

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, bool]


def register_health_check(app: FastAPI, name: str, check: HealthCheck) -> None:
    checks: dict[str, HealthCheck] = app.state.health_checks
    checks[name] = check


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def _gemini_configured(request: Request) -> bool:
    return bool(_settings(request).gemini_api_key.get_secret_value())


async def _api_key_configured(request: Request) -> bool:
    return bool(_settings(request).ai_api_key.get_secret_value())


def _is_allowed(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        addr = ipaddress.ip_address(request.client.host)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return any(
        addr in ipaddress.ip_network(host, strict=False)
        for host in _settings(request).health_allowed_hosts
    )


async def _run(name: str, check: HealthCheck, request: Request) -> bool:
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SEC):
            return await check(request)
    except Exception:
        logger.warning("health check failed", extra={"check": name}, exc_info=True)
        return False


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    if not _is_allowed(request):
        raise not_found()
    checks: dict[str, HealthCheck] = request.app.state.health_checks
    names = list(checks)
    results = await asyncio.gather(*(_run(n, checks[n], request) for n in names))
    values = dict(zip(names, results, strict=True))
    return HealthResponse(status="ok" if all(results) else "degraded", checks=values)


def install_health(app: FastAPI) -> None:
    """기본 확인 항목을 등록하고 라우터를 붙인다."""
    app.state.health_checks = {}
    register_health_check(app, "gemini_configured", _gemini_configured)
    register_health_check(app, "api_key_configured", _api_key_configured)
    app.include_router(router)
