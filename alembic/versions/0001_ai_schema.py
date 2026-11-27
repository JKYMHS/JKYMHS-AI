"""ai 스키마 초기 테이블 (DB.md 3.1, 3.3–3.7)

`place_embeddings`(3.2)는 결정 3 전이라 만들지 않는다.
`jkymhs` 테이블과의 외래 키는 두지 않는다(DB.md 1).

Revision ID: 0001
Revises:
Create Date: 2026-11-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATETIME6 = mysql.DATETIME(fsp=6)


def upgrade() -> None:
    # 3.1 장소 보강 정보
    op.create_table(
        "place_profiles",
        sa.Column("content_id", mysql.BIGINT(), autoincrement=False, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("min_stay_min", mysql.SMALLINT(), nullable=False),
        sa.Column("typical_stay_min", mysql.SMALLINT(), nullable=False),
        sa.Column("has_overview", sa.Boolean(), nullable=False),
        sa.Column("source_hash", mysql.CHAR(length=64), nullable=False),
        sa.Column("source_changed_at", DATETIME6, nullable=False),
        sa.Column("model", sa.String(length=60), nullable=False),
        sa.Column("prompt_version", sa.String(length=20), nullable=False),
        sa.Column("updated_at", DATETIME6, nullable=False),
        sa.PrimaryKeyConstraint("content_id"),
    )

    # 3.3 코스 구성 결과 요약
    op.create_table(
        "course_outputs",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("request_id", mysql.BIGINT(), nullable=False),
        sa.Column("attempt", mysql.TINYINT(), nullable=False),
        sa.Column("courses_json", sa.JSON(), nullable=False),
        sa.Column("self_violations", sa.JSON(), nullable=True),
        sa.Column("remaining_violations", sa.JSON(), nullable=True),
        sa.Column("overlap_max", mysql.DECIMAL(precision=4, scale=3), nullable=False),
        sa.Column("candidate_count", mysql.SMALLINT(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", DATETIME6, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_course_outputs_request_id", "course_outputs", ["request_id"])
    op.create_index("ix_course_outputs_created_at", "course_outputs", ["created_at"])

    # 3.4 LLM 호출 기록
    op.create_table(
        "ai_call_logs",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("request_id", mysql.BIGINT(), nullable=True),
        sa.Column("purpose", mysql.ENUM("COMPOSE", "PROFILE", "EMBED"), nullable=False),
        sa.Column("course_theme", sa.String(length=20), nullable=True),
        sa.Column("model", sa.String(length=60), nullable=False),
        sa.Column("prompt_version", sa.String(length=20), nullable=False),
        sa.Column("thinking_budget", sa.Integer(), nullable=True),
        # DEFAULT FALSE (MySQL은 '0'으로 저장)
        sa.Column("is_batch", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("thoughts_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("finish_reason", sa.String(length=30), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "outcome",
            mysql.ENUM("OK", "REPAIRED", "INVALID", "TIMEOUT", "RATE_LIMITED", "ERROR"),
            nullable=False,
        ),
        sa.Column("violations_json", sa.JSON(), nullable=True),
        sa.Column("created_at", DATETIME6, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_call_logs_request_id", "ai_call_logs", ["request_id"])
    op.create_index("ix_ai_call_logs_created_at", "ai_call_logs", ["created_at"])

    # 3.5 일별 집계
    op.create_table(
        "ai_call_daily_stats",
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=60), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False),
        sa.Column("errors", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", mysql.BIGINT(), nullable=False),
        sa.Column("output_tokens", mysql.BIGINT(), nullable=False),
        sa.Column("thoughts_tokens", mysql.BIGINT(), nullable=False),
        sa.Column("cached_tokens", mysql.BIGINT(), nullable=False),
        sa.Column("cost_usd", mysql.DECIMAL(precision=10, scale=4), nullable=False),
        sa.Column("latency_p50_ms", sa.Integer(), nullable=False),
        sa.Column("latency_p95_ms", sa.Integer(), nullable=False),
        sa.Column("first_pass_rate", mysql.DECIMAL(precision=4, scale=3), nullable=True),
        sa.PrimaryKeyConstraint("stat_date", "purpose", "model"),
    )

    # 3.6 배치 진행 위치
    op.create_table(
        "batch_watermarks",
        sa.Column("job", sa.String(length=40), nullable=False),
        sa.Column("last_changed_at", DATETIME6, nullable=False),
        sa.Column("last_content_id", mysql.BIGINT(), server_default=sa.text("0"), nullable=False),
        sa.Column("updated_at", DATETIME6, nullable=False),
        sa.PrimaryKeyConstraint("job"),
    )

    # 3.7 배치 실행 기록
    op.create_table(
        "batch_runs",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("job", sa.String(length=40), nullable=False),
        sa.Column("status", mysql.ENUM("RUNNING", "SUCCESS", "PARTIAL", "FAILED"), nullable=False),
        sa.Column("started_at", DATETIME6, nullable=False),
        sa.Column("finished_at", DATETIME6, nullable=True),
        sa.Column("processed_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("api_call_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_batch_runs_job_started_at", "batch_runs", ["job", "started_at"])


def downgrade() -> None:
    # 인덱스는 테이블과 함께 지워진다.
    op.drop_table("batch_runs")
    op.drop_table("batch_watermarks")
    op.drop_table("ai_call_daily_stats")
    op.drop_table("ai_call_logs")
    op.drop_table("course_outputs")
    op.drop_table("place_profiles")
