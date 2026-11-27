"""Alembic 실행 환경: `ai` 스키마만 관리한다 (DB.md 6).

- 접속 정보는 `app.config.Settings`(AI_DB_*)에서 읽는다. alembic.ini에 두지 않는다.
- 기본 DB가 `ai`이므로 `alembic_version` 테이블도 `ai` 안에 생긴다.
- `jkymhs`에는 접근하지 않는다.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection

from alembic import context
from app.config import get_settings
from app.db.engine import create_engine, make_db_url
from app.db.models import Base

config = context.config

# 테스트처럼 코드에서 부를 때는 `attributes["configure_logger"] = False`로 앱 로그 설정을 지킨다.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_COMPARE_OPTIONS = {
    "compare_type": True,
    "compare_server_default": True,
}


def run_migrations_offline() -> None:
    """DB에 접속하지 않고 SQL만 출력한다 (`alembic upgrade head --sql`)."""
    context.configure(
        url=make_db_url(get_settings()),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_COMPARE_OPTIONS,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, **_COMPARE_OPTIONS)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_engine(get_settings(), poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
