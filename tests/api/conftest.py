from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app

ClientFactory = Callable[..., AbstractAsyncContextManager[AsyncClient]]


def make_app(**settings: Any) -> FastAPI:
    return create_app(Settings(_env_file=None, **settings))


@asynccontextmanager
async def client_for(app: FastAPI, client_host: str = "127.0.0.1") -> AsyncIterator[AsyncClient]:
    # 처리하지 않은 예외도 응답으로 받아 확인한다.
    transport = ASGITransport(app=app, raise_app_exceptions=False, client=(client_host, 50000))
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        yield client
