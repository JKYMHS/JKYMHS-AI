from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import app, create_app


def test_module_app_exists() -> None:
    assert app.title


async def test_app_serves_openapi() -> None:
    application = create_app(Settings(_env_file=None))
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://t") as client:
        docs = await client.get("/docs")
        schema = await client.get("/openapi.json")

    assert docs.status_code == 200
    assert schema.status_code == 200
    assert schema.json()["info"]["title"] == application.title
