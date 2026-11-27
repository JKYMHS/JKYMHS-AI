import logging

import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from app.api.errors import ApiError
from app.logging import bind_request_id
from tests.api.conftest import client_for, make_app


class Origin(BaseModel):
    lat: float
    lng: float


class Body(BaseModel):
    requestId: int  # noqa: N815 (Spring 계약 이름)
    origin: Origin


def app_with_routes() -> FastAPI:
    app = make_app(ai_api_key="k")

    @app.post("/echo")
    async def echo(body: Body) -> dict[str, int]:
        return {"requestId": body.requestId}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    @app.get("/boom-with-id")
    async def boom_with_id() -> None:
        bind_request_id(77)
        raise RuntimeError("boom")

    @app.get("/api-error")
    async def api_error() -> None:
        raise ApiError(503, "LLM_UNAVAILABLE", "코스를 만들지 못했습니다")

    return app


async def test_validation_error_is_422_without_values() -> None:
    payload = {"requestId": "not-a-number", "origin": {"lat": 37.5665123, "lng": "east"}}
    async with client_for(app_with_routes()) as client:
        resp = await client.post("/echo", json=payload)

    assert resp.status_code == 422
    body = resp.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == "INVALID_REQUEST"
    assert "body.requestId" in body["message"]
    assert "body.origin.lng" in body["message"]
    # 요청 값(출발지 좌표 등)은 응답에 넣지 않는다.
    for value in ("not-a-number", "37.5665123", "east"):
        assert value not in resp.text


async def test_validation_error_missing_and_bad_json() -> None:
    async with client_for(app_with_routes()) as client:
        missing = await client.post("/echo", json={})
        bad_json = await client.post(
            "/echo", content=b"{not json", headers={"Content-Type": "application/json"}
        )

    assert missing.status_code == 422
    assert missing.json()["code"] == "INVALID_REQUEST"
    assert "body.requestId(missing)" in missing.json()["message"]
    assert bad_json.status_code == 422
    assert bad_json.json()["code"] == "INVALID_REQUEST"


async def test_validation_message_caps_field_count() -> None:
    app = make_app()

    class Many(BaseModel):
        a: int
        b: int
        c: int
        d: int
        e: int
        f: int
        g: int

    @app.post("/many")
    async def many(body: Many) -> None:
        return None

    async with client_for(app) as client:
        resp = await client.post("/many", json={})
    assert resp.status_code == 422
    assert resp.json()["message"].endswith("외 2건")


async def test_unhandled_error_is_500_without_internals(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR, logger="app.api.errors"):
        async with client_for(app_with_routes()) as client:
            resp = await client.get("/boom")

    assert resp.status_code == 500
    assert resp.json() == {"code": "INTERNAL", "message": "Internal Server Error"}
    assert "secret internal detail" not in resp.text
    assert "Traceback" not in resp.text
    # 스택은 로그에만 남는다.
    errors = [r for r in caplog.records if r.name == "app.api.errors"]
    assert len(errors) == 1
    assert errors[0].exc_info is not None


async def test_unhandled_error_logged_with_status_500(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="app.access"):
        async with client_for(app_with_routes()) as client:
            await client.get("/boom")
    access = [r for r in caplog.records if r.name == "app.access"]
    assert [getattr(r, "status", None) for r in access] == [500]


async def test_api_error_uses_given_status_and_code() -> None:
    async with client_for(app_with_routes()) as client:
        resp = await client.get("/api-error")
    assert resp.status_code == 503
    assert resp.json() == {"code": "LLM_UNAVAILABLE", "message": "코스를 만들지 못했습니다"}


async def test_unknown_route_and_method_use_error_format() -> None:
    async with client_for(app_with_routes()) as client:
        missing = await client.get("/nope")
        wrong_method = await client.get("/echo")

    assert missing.status_code == 404
    assert missing.json() == {"code": "NOT_FOUND", "message": "Not Found"}
    assert wrong_method.status_code == 405
    assert wrong_method.json()["code"] == "METHOD_NOT_ALLOWED"


async def test_unhandled_error_log_keeps_request_id(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="app.api.errors"):
        async with client_for(app_with_routes()) as client:
            resp = await client.get("/boom-with-id")
    assert resp.status_code == 500
    errors = [r for r in caplog.records if r.name == "app.api.errors"]
    assert [getattr(r, "request_id", None) for r in errors] == [77]
