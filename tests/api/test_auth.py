import logging

import pytest
from fastapi import APIRouter, Depends, FastAPI

from app.api.auth import require_api_key, warn_if_api_key_missing
from app.config import Settings
from tests.api.conftest import client_for, make_app

KEY = "test-key-123"


def app_with_protected_route(api_key: str) -> FastAPI:
    app = make_app(ai_api_key=api_key)
    router = APIRouter(dependencies=[Depends(require_api_key)])

    @router.post("/protected")
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(router)
    return app


def assert_unauthorized(resp_json: dict[str, str], headers: dict[str, str]) -> None:
    assert resp_json["code"] == "UNAUTHORIZED"
    assert set(resp_json) == {"code", "message"}
    assert headers["www-authenticate"] == "Bearer"


async def test_missing_header_is_401() -> None:
    async with client_for(app_with_protected_route(KEY)) as client:
        resp = await client.post("/protected")
    assert resp.status_code == 401
    assert_unauthorized(resp.json(), dict(resp.headers))


@pytest.mark.parametrize(
    "header",
    [
        "Bearer wrong-key",
        f"Bearer {KEY}x",
        f"Basic {KEY}",
        KEY,
        "Bearer ",
        "Bearer 키".encode(),  # ASCII가 아닌 값도 500이 아니라 401
    ],
)
async def test_wrong_header_is_401(header: str | bytes) -> None:
    async with client_for(app_with_protected_route(KEY)) as client:
        resp = await client.post("/protected", headers={"Authorization": header})
    assert resp.status_code == 401
    assert_unauthorized(resp.json(), dict(resp.headers))
    assert KEY not in resp.text


@pytest.mark.parametrize("scheme", ["Bearer", "bearer"])
async def test_correct_key_passes(scheme: str) -> None:
    async with client_for(app_with_protected_route(KEY)) as client:
        resp = await client.post("/protected", headers={"Authorization": f"{scheme} {KEY}"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.parametrize("header", [None, "Bearer ", "Bearer anything"])
async def test_unset_server_key_rejects_everything(header: str | None) -> None:
    headers = {"Authorization": header} if header is not None else {}
    async with client_for(app_with_protected_route("")) as client:
        resp = await client.post("/protected", headers=headers)
    assert resp.status_code == 401
    assert_unauthorized(resp.json(), dict(resp.headers))


def test_warns_when_key_missing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="app.api.auth"):
        warn_if_api_key_missing(Settings(_env_file=None, ai_api_key=""))
    assert [r.levelname for r in caplog.records] == ["WARNING"]

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="app.api.auth"):
        warn_if_api_key_missing(Settings(_env_file=None, ai_api_key=KEY))
    assert caplog.records == []
