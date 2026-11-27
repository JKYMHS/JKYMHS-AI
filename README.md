# JKYMHS-AI

어디갈래 AI 서버. Spring이 고른 후보로 여행 코스를 짜고(`POST /v1/courses`), 장소 정보 보강 배치를 돌립니다. 정책과 설계는 [`docs/`](docs/)를 봅니다.

## 로컬 실행

[uv](https://docs.astral.sh/uv/)와 Python 3.12가 필요합니다.

```sh
uv sync                      # 의존성 설치 (.venv)
cp .env.example .env         # 설정값 채우기 (비밀값은 커밋하지 않음)
uv run uvicorn app.main:app --reload --port 8000
# http://localhost:8000/docs
```

## 검사와 테스트

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
```

## Docker

```sh
docker build -t jkymhs-ai .
docker run --rm -p 8000:8000 --env-file .env jkymhs-ai
```

워커 수는 `UVICORN_WORKERS`(기본 2)로 정합니다.
