from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.db.engine import create_engine, create_session_factory, make_db_url


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        ai_db_host="db.local",
        ai_db_port=3307,
        ai_db_user="ai_server",
        ai_db_password="db-secret",
        ai_db_name="ai",
    )


def test_url_from_settings() -> None:
    url = make_db_url(_settings())
    assert url.drivername == "mysql+asyncmy"
    assert url.host == "db.local"
    assert url.port == 3307
    assert url.username == "ai_server"
    assert url.password == "db-secret"
    assert url.database == "ai"
    assert url.query["charset"] == "utf8mb4"


def test_password_hidden_in_url_and_engine() -> None:
    url = make_db_url(_settings())
    engine = create_engine(_settings())
    try:
        assert isinstance(engine, AsyncEngine)
        for text in (str(url), repr(url), repr(engine), str(engine.url), repr(engine.url)):
            assert "db-secret" not in text
    finally:
        engine.sync_engine.dispose()


def test_empty_password_omitted() -> None:
    url = make_db_url(Settings(_env_file=None, ai_db_user="u", ai_db_password=""))
    assert url.password is None


def test_session_factory_keeps_objects_after_commit() -> None:
    engine = create_engine(_settings())
    try:
        factory = create_session_factory(engine)
        assert factory.kw["expire_on_commit"] is False
    finally:
        engine.sync_engine.dispose()
