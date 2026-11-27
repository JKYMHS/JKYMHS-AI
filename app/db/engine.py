"""`ai` 스키마 연결 (DB.md 1, 6).

설정(`AI_DB_*`)으로 async 엔진과 세션 팩토리를 만든다. 드라이버는 `asyncmy`.
연결 정보는 `URL` 객체로 넘긴다. `URL`의 repr·str은 비밀번호를 `***`로 가리므로
엔진 repr과 로그에 비밀번호가 드러나지 않는다. 연결 문자열을 직접 만들거나 출력하지 않는다.
"""

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings


def make_db_url(settings: Settings) -> URL:
    """`ai` 스키마 접속 URL. 기본 DB가 `ai`이므로 `alembic_version`도 `ai`에 생긴다."""
    return URL.create(
        drivername="mysql+asyncmy",
        username=settings.ai_db_user,
        password=settings.ai_db_password.get_secret_value() or None,
        host=settings.ai_db_host,
        port=settings.ai_db_port,
        database=settings.ai_db_name,
        query={"charset": "utf8mb4"},
    )


def create_engine(settings: Settings, **kwargs: object) -> AsyncEngine:
    """`ai` 스키마용 async 엔진.

    같은 인스턴스의 MySQL `wait_timeout`에 끊긴 연결을 쓰지 않도록 꺼내기 전에 확인하고,
    한 시간마다 연결을 새로 만든다. `kwargs`로 기본값을 덮어쓸 수 있다(예: `poolclass`).
    """
    options: dict[str, object] = {"pool_pre_ping": True, "pool_recycle": 3600}
    options.update(kwargs)
    return create_async_engine(make_db_url(settings), **options)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
