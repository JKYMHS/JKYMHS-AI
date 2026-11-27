import contextvars
import json
import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.logging import JsonFormatter, bind_request_id, configure_logging, get_request_id
from app.main import create_app


def _records(caplog: pytest.LogCaptureFixture, name: str) -> list[dict[str, object]]:
    formatter = JsonFormatter()
    return [json.loads(formatter.format(r)) for r in caplog.records if r.name == name]


def test_formatter_emits_one_json_line_with_request_id() -> None:
    configure_logging()

    def run() -> str:
        bind_request_id(123)
        record = logging.getLogRecordFactory()(
            "t", logging.INFO, __file__, 1, "안녕 %s", ("세계",), None
        )
        record.stage = "compose"
        return JsonFormatter().format(record)

    line = contextvars.copy_context().run(run)

    assert "\n" not in line
    data = json.loads(line)
    assert data["request_id"] == 123
    assert data["msg"] == "안녕 세계"
    assert data["level"] == "INFO"
    assert data["stage"] == "compose"


async def test_request_id_bound_in_handler_appears_in_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app: FastAPI = create_app(Settings(_env_file=None))
    handler_logger = logging.getLogger("test.handler")

    @app.post("/echo")
    async def echo(body: dict[str, object]) -> dict[str, object]:
        bind_request_id(body["requestId"])  # type: ignore[arg-type]
        handler_logger.info("handled")
        return {"ok": True}

    caplog.set_level(logging.INFO)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(
            "/echo?lat=37.5", json={"requestId": 777, "origin": {"lat": 37.57, "lng": 126.98}}
        )
    assert resp.status_code == 200

    [handled] = _records(caplog, "test.handler")
    assert handled["request_id"] == 777

    [access] = _records(caplog, "app.access")
    assert access["request_id"] == 777
    assert access["method"] == "POST"
    assert access["path"] == "/echo"
    assert access["status"] == 200
    assert isinstance(access["duration_ms"], float)
    # 본문(출발지 좌표)과 쿼리 문자열은 남기지 않는다.
    raw = json.dumps(access)
    assert "37.57" not in raw
    assert "126.98" not in raw
    assert "lat=" not in raw


async def test_request_id_does_not_leak_between_requests(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app: FastAPI = create_app(Settings(_env_file=None))

    @app.get("/bind")
    async def bind() -> dict[str, object]:
        bind_request_id(1)
        return {}

    @app.get("/plain")
    async def plain() -> dict[str, object]:
        return {"request_id": get_request_id()}

    caplog.set_level(logging.INFO)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        await client.get("/bind")
        resp = await client.get("/plain")

    assert resp.json() == {"request_id": None}
    access = _records(caplog, "app.access")
    assert [a["request_id"] for a in access] == [1, None]
