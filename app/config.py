"""설정값 (TRD 11장).

환경 변수(또는 `.env`)에서 읽는다. 키 이름은 대소문자를 가리지 않는다.
비밀값은 `SecretStr`로 두어 로그·repr에 드러나지 않게 한다.
"""

import ipaddress
from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 인증·비밀값: 저장소에 넣지 않는다. 기본값은 빈 값.
    ai_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")

    # Gemini 모델 (TRD 1.3, 11)
    gemini_compose_model: str = "gemini-2.5-flash"
    gemini_batch_model: str = "gemini-2.5-flash"
    gemini_embed_model: str | None = None  # TRD 11: 확인 필요

    # 코스 구성 (TRD 5.7, 11)
    compose_deadline_sec: float = Field(default=18, gt=0)
    compose_call_timeout_sec: float = Field(default=12, gt=0)
    compose_thinking_budget: int = Field(default=0, ge=0)
    compose_max_output_tokens: int = Field(default=1024, gt=0)
    llm_concurrency: int = Field(default=24, gt=0)
    course_overlap_max: float = Field(default=0.5, ge=0, le=1)
    reason_max_chars: int = Field(default=40, gt=0)
    prompt_compose_version: str | None = None  # TRD 11: 최신 검증 버전 (프롬프트 작업에서 정함)

    # 운영 (TRD 10, 11)
    uvicorn_workers: int = Field(default=2, gt=0)
    gemini_monthly_budget_usd: float | None = Field(default=None, ge=0)  # 팀 결정
    log_level: str = "INFO"
    # `GET /health`에 응답할 클라이언트 주소 (TRD 4, 8). 쉼표로 구분하며 CIDR도 받는다.
    # Docker 브리지처럼 접근 경로가 다르면 그 주소를 더한다(예: `127.0.0.1,::1,172.17.0.1`).
    health_allowed_hosts: Annotated[list[str], NoDecode] = ["127.0.0.1", "::1"]

    # DB (DB.md): AI 전용 계정. `ai` 스키마에 쓰고, 배치만 `jkymhs`를 읽는다.
    ai_db_host: str = "localhost"
    ai_db_port: int = 3306
    ai_db_user: str = ""
    ai_db_password: SecretStr = SecretStr("")
    ai_db_name: str = "ai"
    jkymhs_db_name: str = "jkymhs"

    @field_validator("health_allowed_hosts", mode="before")
    @classmethod
    def _split_hosts(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("health_allowed_hosts")
    @classmethod
    def _check_hosts(cls, value: list[str]) -> list[str]:
        for host in value:
            ipaddress.ip_network(host, strict=False)  # 잘못된 주소면 ValueError
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
