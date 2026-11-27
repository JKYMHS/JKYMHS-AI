import asyncio

import pytest
from fastapi import Request

from app.api import health as health_module
from app.api.health import register_health_check
from tests.api.conftest import client_for, make_app


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "::ffff:127.0.0.1"])
async def test_localhost_allowed(host: str) -> None:
    async with client_for(make_app(), client_host=host) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.parametrize("host", ["10.0.0.5", "172.17.0.1", "2001:db8::1", "testclient"])
async def test_other_hosts_get_404_like_unknown_route(host: str) -> None:
    async with client_for(make_app(), client_host=host) as client:
        resp = await client.get("/health")
        unknown = await client.get("/no-such-path")
    assert resp.status_code == 404
    assert resp.json() == unknown.json()


async def test_allowed_hosts_from_settings_accepts_cidr() -> None:
    app = make_app(health_allowed_hosts="127.0.0.1,172.17.0.0/16")
    async with client_for(app, client_host="172.17.0.1") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


def test_allowed_hosts_env_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import Settings

    monkeypatch.setenv("HEALTH_ALLOWED_HOSTS", " 127.0.0.1 , ::1,172.17.0.1 ")
    assert Settings(_env_file=None).health_allowed_hosts == ["127.0.0.1", "::1", "172.17.0.1"]
    monkeypatch.delenv("HEALTH_ALLOWED_HOSTS")
    assert Settings(_env_file=None).health_allowed_hosts == ["127.0.0.1", "::1"]
    monkeypatch.setenv("HEALTH_ALLOWED_HOSTS", "localhost")
    with pytest.raises(ValueError, match="health_allowed_hosts"):
        Settings(_env_file=None)


async def test_ok_when_all_configured() -> None:
    async with client_for(make_app(ai_api_key="k", gemini_api_key="g")) as client:
        resp = await client.get("/health")
    assert resp.json() == {
        "status": "ok",
        "checks": {"gemini_configured": True, "api_key_configured": True},
    }


async def test_degraded_when_something_missing() -> None:
    async with client_for(make_app(ai_api_key="k", gemini_api_key="")) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "degraded",
        "checks": {"gemini_configured": False, "api_key_configured": True},
    }


async def test_health_needs_no_auth() -> None:
    async with client_for(make_app(ai_api_key="k", gemini_api_key="g")) as client:
        resp = await client.get("/health", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 200


async def test_registered_checks_are_included(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_module, "CHECK_TIMEOUT_SEC", 0.05)
    app = make_app(ai_api_key="k", gemini_api_key="g")

    async def passes(request: Request) -> bool:
        return True

    async def raises(request: Request) -> bool:
        raise ConnectionError("db down")

    async def hangs(request: Request) -> bool:
        await asyncio.sleep(10)
        return True

    register_health_check(app, "extra", passes)
    async with client_for(app) as client:
        ok = await client.get("/health")
    assert ok.json()["status"] == "ok"
    assert ok.json()["checks"]["extra"] is True

    register_health_check(app, "db", raises)
    register_health_check(app, "slow", hangs)
    async with client_for(app) as client:
        bad = await client.get("/health")
    assert bad.status_code == 200
    assert bad.json()["status"] == "degraded"
    assert bad.json()["checks"]["db"] is False
    assert bad.json()["checks"]["slow"] is False
    assert "db down" not in bad.text
