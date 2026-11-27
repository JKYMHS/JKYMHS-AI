"""`ai` 스키마 모델 (DB.md 3).

열 타입·NULL·기본값·인덱스는 DB.md 3장의 DDL과 같다. 모든 시각은 `DATETIME(6)`(KST).
`jkymhs` 테이블은 외래 키 없이 값으로만 참조한다(DB.md 1).
`place_embeddings`(3.2)는 결정 3 전이라 만들지 않는다.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, Date, Index, Integer, MetaData, String, Text, text
from sqlalchemy.dialects.mysql import BIGINT, CHAR, DATETIME, DECIMAL, ENUM, SMALLINT, TINYINT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 인덱스 이름을 고정해 autogenerate와 마이그레이션이 같은 이름을 쓰게 한다.
NAMING_CONVENTION = {"ix": "ix_%(table_name)s_%(column_0_N_name)s"}

DATETIME6 = DATETIME(fsp=6)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class CallPurpose(StrEnum):
    COMPOSE = "COMPOSE"
    PROFILE = "PROFILE"
    EMBED = "EMBED"


class CallOutcome(StrEnum):
    OK = "OK"
    REPAIRED = "REPAIRED"
    INVALID = "INVALID"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    ERROR = "ERROR"


class BatchRunStatus(StrEnum):
    """`jkymhs.batch_job_logs.status`와 같은 값."""

    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


def _enum(cls: type[StrEnum]) -> ENUM:
    """MySQL 네이티브 ENUM. 값 순서는 DB.md DDL과 같다."""
    return ENUM(cls, values_callable=lambda e: [m.value for m in e])


class PlaceProfile(Base):
    """3.1 장소 보강 정보."""

    __tablename__ = "place_profiles"

    content_id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tags_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    min_stay_min: Mapped[int] = mapped_column(SMALLINT, nullable=False)
    typical_stay_min: Mapped[int] = mapped_column(SMALLINT, nullable=False)
    has_overview: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    source_changed_at: Mapped[datetime] = mapped_column(DATETIME6, nullable=False)
    model: Mapped[str] = mapped_column(String(60), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME6, nullable=False)


class CourseOutput(Base):
    """3.3 코스 구성 결과 요약. 사용자 정보와 출발지는 넣지 않는다. 90일 보관."""

    __tablename__ = "course_outputs"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(BIGINT, nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(TINYINT, nullable=False)
    courses_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    self_violations: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    remaining_violations: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    overlap_max: Mapped[Decimal] = mapped_column(DECIMAL(4, 3), nullable=False)
    candidate_count: Mapped[int] = mapped_column(SMALLINT, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME6, nullable=False, index=True)


class AiCallLog(Base):
    """3.4 LLM 호출 기록. 프롬프트와 응답 원문은 저장하지 않는다. 90일 보관."""

    __tablename__ = "ai_call_logs"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    request_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True, index=True)
    purpose: Mapped[CallPurpose] = mapped_column(_enum(CallPurpose), nullable=False)
    course_theme: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model: Mapped[str] = mapped_column(String(60), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    thinking_budget: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # DB.md는 `DEFAULT FALSE`. MySQL은 이를 '0'으로 저장하므로 같은 값으로 적어 비교 차이를 없앤다.
    is_batch: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thoughts_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[CallOutcome] = mapped_column(_enum(CallOutcome), nullable=False)
    violations_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DATETIME6, nullable=False, index=True)


class AiCallDailyStat(Base):
    """3.5 일별 집계. 계속 보관."""

    __tablename__ = "ai_call_daily_stats"

    stat_date: Mapped[date] = mapped_column(Date, primary_key=True)
    purpose: Mapped[str] = mapped_column(String(20), primary_key=True)
    model: Mapped[str] = mapped_column(String(60), primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, nullable=False)
    errors: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(BIGINT, nullable=False)
    output_tokens: Mapped[int] = mapped_column(BIGINT, nullable=False)
    thoughts_tokens: Mapped[int] = mapped_column(BIGINT, nullable=False)
    cached_tokens: Mapped[int] = mapped_column(BIGINT, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(DECIMAL(10, 4), nullable=False)
    latency_p50_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_p95_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    first_pass_rate: Mapped[Decimal | None] = mapped_column(DECIMAL(4, 3), nullable=True)


class BatchWatermark(Base):
    """3.6 배치 진행 위치. `job`은 'profile', 'embed'."""

    __tablename__ = "batch_watermarks"

    job: Mapped[str] = mapped_column(String(40), primary_key=True)
    last_changed_at: Mapped[datetime] = mapped_column(DATETIME6, nullable=False)
    last_content_id: Mapped[int] = mapped_column(BIGINT, nullable=False, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(DATETIME6, nullable=False)


class BatchRun(Base):
    """3.7 배치 실행 기록."""

    __tablename__ = "batch_runs"
    __table_args__ = (Index("ix_batch_runs_job_started_at", "job", "started_at"),)

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    job: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[BatchRunStatus] = mapped_column(_enum(BatchRunStatus), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DATETIME6, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DATETIME6, nullable=True)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    api_call_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
