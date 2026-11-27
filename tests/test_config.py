import pytest
from pydantic import SecretStr

from app.config import Settings

# TRD 11장의 키 전부
TRD_KEYS = {
    "AI_API_KEY",
    "GEMINI_COMPOSE_MODEL",
    "GEMINI_BATCH_MODEL",
    "GEMINI_EMBED_MODEL",
    "COMPOSE_DEADLINE_SEC",
    "COMPOSE_CALL_TIMEOUT_SEC",
    "COMPOSE_THINKING_BUDGET",
    "COMPOSE_MAX_OUTPUT_TOKENS",
    "LLM_CONCURRENCY",
    "COURSE_OVERLAP_MAX",
    "REASON_MAX_CHARS",
    "PROMPT_COMPOSE_VERSION",
    "UVICORN_WORKERS",
    "GEMINI_MONTHLY_BUDGET_USD",
}


def test_all_trd_keys_defined() -> None:
    fields = {name.upper() for name in Settings.model_fields}
    assert fields >= TRD_KEYS


def test_defaults_match_trd(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in TRD_KEYS:
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)

    assert s.gemini_compose_model == "gemini-2.5-flash"
    assert s.gemini_batch_model == "gemini-2.5-flash"
    assert s.compose_deadline_sec == 18
    assert s.compose_call_timeout_sec == 12
    assert s.compose_thinking_budget == 0
    assert s.compose_max_output_tokens == 1024
    assert s.llm_concurrency == 24
    assert s.course_overlap_max == 0.5
    assert s.reason_max_chars == 40
    assert s.uvicorn_workers == 2
    assert s.ai_db_name == "ai"
    assert s.jkymhs_db_name == "jkymhs"
    assert s.ai_api_key.get_secret_value() == ""


def test_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("COMPOSE_DEADLINE_SEC", "15")
    monkeypatch.setenv("GEMINI_COMPOSE_MODEL", "gemini-x")
    monkeypatch.setenv("AI_DB_PORT", "3307")

    s = Settings(_env_file=None)

    assert s.ai_api_key.get_secret_value() == "test-key"
    assert s.compose_deadline_sec == 15
    assert s.gemini_compose_model == "gemini-x"
    assert s.ai_db_port == 3307


def test_secrets_hidden_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_API_KEY", "top-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
    monkeypatch.setenv("AI_DB_PASSWORD", "db-secret")

    s = Settings(_env_file=None)

    assert isinstance(s.ai_db_password, SecretStr)
    text = repr(s) + str(s.model_dump())
    for secret in ("top-secret", "gemini-secret", "db-secret"):
        assert secret not in text


def test_rejects_invalid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COURSE_OVERLAP_MAX", "1.5")
    with pytest.raises(ValueError, match="course_overlap_max"):
        Settings(_env_file=None)
