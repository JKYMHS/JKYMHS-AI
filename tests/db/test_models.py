"""모델 메타데이터가 DB.md 3장 DDL과 같은지 확인한다 (DB 없이)."""

from typing import Any

import pytest
from sqlalchemy import Table
from sqlalchemy.dialects import mysql

from app.db.models import Base, BatchRunStatus, CallOutcome, CallPurpose

DIALECT = mysql.dialect()  # type: ignore[no-untyped-call]

# 테이블 → 열 → (MySQL 타입, NULL 허용, 서버 기본값). DB.md 3.1, 3.3–3.7.
EXPECTED: dict[str, dict[str, tuple[str, bool, str | None]]] = {
    "place_profiles": {
        "content_id": ("BIGINT", False, None),
        "description": ("TEXT", False, None),
        "tags_json": ("JSON", False, None),
        "min_stay_min": ("SMALLINT", False, None),
        "typical_stay_min": ("SMALLINT", False, None),
        "has_overview": ("BOOL", False, None),
        "source_hash": ("CHAR(64)", False, None),
        "source_changed_at": ("DATETIME(6)", False, None),
        "model": ("VARCHAR(60)", False, None),
        "prompt_version": ("VARCHAR(20)", False, None),
        "updated_at": ("DATETIME(6)", False, None),
    },
    "course_outputs": {
        "id": ("BIGINT", False, None),
        "request_id": ("BIGINT", False, None),
        "attempt": ("TINYINT", False, None),
        "courses_json": ("JSON", False, None),
        "self_violations": ("JSON", True, None),
        "remaining_violations": ("JSON", True, None),
        "overlap_max": ("DECIMAL(4, 3)", False, None),
        "candidate_count": ("SMALLINT", False, None),
        "latency_ms": ("INTEGER", False, None),
        "created_at": ("DATETIME(6)", False, None),
    },
    "ai_call_logs": {
        "id": ("BIGINT", False, None),
        "request_id": ("BIGINT", True, None),
        "purpose": ("ENUM('COMPOSE','PROFILE','EMBED')", False, None),
        "course_theme": ("VARCHAR(20)", True, None),
        "model": ("VARCHAR(60)", False, None),
        "prompt_version": ("VARCHAR(20)", False, None),
        "thinking_budget": ("INTEGER", True, None),
        "is_batch": ("BOOL", False, "0"),
        "prompt_tokens": ("INTEGER", True, None),
        "output_tokens": ("INTEGER", True, None),
        "thoughts_tokens": ("INTEGER", True, None),
        "cached_tokens": ("INTEGER", True, None),
        "finish_reason": ("VARCHAR(30)", True, None),
        "latency_ms": ("INTEGER", False, None),
        "outcome": (
            "ENUM('OK','REPAIRED','INVALID','TIMEOUT','RATE_LIMITED','ERROR')",
            False,
            None,
        ),
        "violations_json": ("JSON", True, None),
        "created_at": ("DATETIME(6)", False, None),
    },
    "ai_call_daily_stats": {
        "stat_date": ("DATE", False, None),
        "purpose": ("VARCHAR(20)", False, None),
        "model": ("VARCHAR(60)", False, None),
        "calls": ("INTEGER", False, None),
        "errors": ("INTEGER", False, None),
        "prompt_tokens": ("BIGINT", False, None),
        "output_tokens": ("BIGINT", False, None),
        "thoughts_tokens": ("BIGINT", False, None),
        "cached_tokens": ("BIGINT", False, None),
        "cost_usd": ("DECIMAL(10, 4)", False, None),
        "latency_p50_ms": ("INTEGER", False, None),
        "latency_p95_ms": ("INTEGER", False, None),
        "first_pass_rate": ("DECIMAL(4, 3)", True, None),
    },
    "batch_watermarks": {
        "job": ("VARCHAR(40)", False, None),
        "last_changed_at": ("DATETIME(6)", False, None),
        "last_content_id": ("BIGINT", False, "0"),
        "updated_at": ("DATETIME(6)", False, None),
    },
    "batch_runs": {
        "id": ("BIGINT", False, None),
        "job": ("VARCHAR(40)", False, None),
        "status": ("ENUM('RUNNING','SUCCESS','PARTIAL','FAILED')", False, None),
        "started_at": ("DATETIME(6)", False, None),
        "finished_at": ("DATETIME(6)", True, None),
        "processed_count": ("INTEGER", False, "0"),
        "failed_count": ("INTEGER", False, "0"),
        "api_call_count": ("INTEGER", False, "0"),
        "error_message": ("VARCHAR(1000)", True, None),
    },
}

PRIMARY_KEYS = {
    "place_profiles": ["content_id"],
    "course_outputs": ["id"],
    "ai_call_logs": ["id"],
    "ai_call_daily_stats": ["stat_date", "purpose", "model"],
    "batch_watermarks": ["job"],
    "batch_runs": ["id"],
}

AUTO_INCREMENT = {"course_outputs", "ai_call_logs", "batch_runs"}

INDEXES = {
    "course_outputs": {"ix_course_outputs_request_id": ["request_id"],
                       "ix_course_outputs_created_at": ["created_at"]},
    "ai_call_logs": {"ix_ai_call_logs_request_id": ["request_id"],
                     "ix_ai_call_logs_created_at": ["created_at"]},
    "batch_runs": {"ix_batch_runs_job_started_at": ["job", "started_at"]},
}  # fmt: skip


def _table(name: str) -> Table:
    return Base.metadata.tables[name]


def _server_default(column: Any) -> str | None:
    default = column.server_default
    return None if default is None else str(default.arg)


def test_tables_are_exactly_db_md() -> None:
    assert set(Base.metadata.tables) == set(EXPECTED)


def test_place_embeddings_not_created() -> None:
    # DB.md 3.2: 결정 3 전에는 만들지 않는다.
    assert "place_embeddings" not in Base.metadata.tables


@pytest.mark.parametrize("table_name", sorted(EXPECTED))
def test_columns(table_name: str) -> None:
    table = _table(table_name)
    expected = EXPECTED[table_name]
    assert [c.name for c in table.columns] == list(expected)
    for name, (type_sql, nullable, default) in expected.items():
        column = table.columns[name]
        assert column.type.compile(dialect=DIALECT) == type_sql, name
        assert column.nullable is nullable, name
        assert _server_default(column) == default, name


@pytest.mark.parametrize("table_name", sorted(EXPECTED))
def test_primary_key_and_auto_increment(table_name: str) -> None:
    table = _table(table_name)
    assert [c.name for c in table.primary_key.columns] == PRIMARY_KEYS[table_name]
    auto = table.autoincrement_column
    if table_name in AUTO_INCREMENT:
        assert auto is not None
        assert auto.name == "id"
    else:
        assert auto is None


@pytest.mark.parametrize("table_name", sorted(EXPECTED))
def test_indexes(table_name: str) -> None:
    table = _table(table_name)
    actual = {ix.name: [c.name for c in ix.columns] for ix in table.indexes}
    assert actual == INDEXES.get(table_name, {})
    assert not any(ix.unique for ix in table.indexes)


def test_no_foreign_keys() -> None:
    # DB.md 1: jkymhs는 값으로만 참조한다.
    for table in Base.metadata.tables.values():
        assert not table.foreign_keys, table.name


def test_enum_values_match_ddl() -> None:
    assert [m.value for m in CallPurpose] == ["COMPOSE", "PROFILE", "EMBED"]
    assert [m.value for m in CallOutcome] == [
        "OK",
        "REPAIRED",
        "INVALID",
        "TIMEOUT",
        "RATE_LIMITED",
        "ERROR",
    ]
    assert [m.value for m in BatchRunStatus] == ["RUNNING", "SUCCESS", "PARTIAL", "FAILED"]
