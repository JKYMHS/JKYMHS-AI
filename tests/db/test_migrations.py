"""마이그레이션이 모델과 같은 DDL을 만드는지 확인한다 (DB 없이, offline SQL).

실제 DB에서의 확인은 `alembic upgrade head` 뒤 `alembic check`로 한다(README).
"""

import io
import re
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

from alembic import command
from app.db.models import Base

ROOT = Path(__file__).resolve().parents[2]
DIALECT = mysql.dialect()  # type: ignore[no-untyped-call]


def _config(buffer: io.StringIO | None = None) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"), output_buffer=buffer or io.StringIO())
    cfg.attributes["configure_logger"] = False
    return cfg


def _normalize(sql: str) -> list[str]:
    """문장 하나를 공백·끝 쉼표를 뺀 줄 목록으로."""
    lines = (line.strip().rstrip(",").rstrip(";") for line in sql.strip().splitlines())
    return sorted(line for line in lines if line)


@pytest.fixture(scope="module")
def upgrade_sql() -> str:
    buffer = io.StringIO()
    command.upgrade(_config(buffer), "head", sql=True)
    return buffer.getvalue()


def test_single_head_0001() -> None:
    script = ScriptDirectory.from_config(_config())
    assert script.get_heads() == ["0001"]


def test_creates_tables_in_ai_only(upgrade_sql: str) -> None:
    created = set(re.findall(r"CREATE TABLE (\w+)", upgrade_sql))
    assert created == set(Base.metadata.tables) | {"alembic_version"}
    assert "place_embeddings" not in upgrade_sql
    assert "jkymhs" not in upgrade_sql
    assert "FOREIGN KEY" not in upgrade_sql


def test_migration_ddl_matches_models(upgrade_sql: str) -> None:
    statements = {
        m.group(1): _normalize(m.group(0))
        for m in re.finditer(r"CREATE TABLE (\w+) \(.*?\n\);", upgrade_sql, re.S)
    }
    for table in Base.metadata.sorted_tables:
        expected = _normalize(str(CreateTable(table).compile(dialect=DIALECT)) + ";")
        assert statements[table.name] == expected, table.name


def test_migration_indexes_match_models(upgrade_sql: str) -> None:
    actual = {line.strip() for line in re.findall(r"^CREATE INDEX .*?;$", upgrade_sql, re.M)}
    expected = {
        str(CreateIndex(ix).compile(dialect=DIALECT)) + ";"
        for table in Base.metadata.sorted_tables
        for ix in table.indexes
    }
    assert actual == expected


def test_downgrade_drops_everything() -> None:
    buffer = io.StringIO()
    command.downgrade(_config(buffer), "0001:base", sql=True)
    sql = buffer.getvalue()
    dropped = set(re.findall(r"DROP TABLE (\w+)", sql))
    assert dropped == set(Base.metadata.tables)
    # 버전 기록은 지우고 `alembic_version` 테이블은 남긴다(Alembic 기본 동작).
    assert "DELETE FROM alembic_version" in sql
