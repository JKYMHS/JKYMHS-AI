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

## DB 마이그레이션

`ai` 스키마는 Alembic으로 관리합니다([`docs/DB.md`](docs/DB.md) 3, 6장). 접속 정보는 `.env`의 `AI_DB_*`에서 읽고, `alembic_version`도 `ai` 스키마에 생깁니다. `jkymhs`에는 쓰지 않습니다.

```sh
uv run alembic upgrade head          # 최신으로 적용
uv run alembic downgrade -1          # 한 단계 되돌리기 (base: 전부 삭제)
uv run alembic check                 # 모델과 DB 차이 확인 (차이가 없어야 함)
uv run alembic upgrade head --sql    # DB에 접속하지 않고 SQL만 출력
```

모델(`app/db/models.py`)을 바꾸면 `uv run alembic revision --autogenerate -m "<요약>"`로 초안을 만들고 검토한 뒤 커밋합니다. 로컬 검증에는 임시 MySQL을 씁니다.

```sh
docker run -d --rm --name ai-mysql -e MYSQL_ROOT_PASSWORD=test -e MYSQL_DATABASE=ai -p 127.0.0.1:33306:3306 mysql:8.4
AI_DB_HOST=127.0.0.1 AI_DB_PORT=33306 AI_DB_USER=root AI_DB_PASSWORD=test uv run alembic upgrade head
docker stop ai-mysql
```

## Docker

```sh
docker build -t jkymhs-ai .
docker run --rm -p 8000:8000 --env-file .env jkymhs-ai
```

워커 수는 `UVICORN_WORKERS`(기본 2)로 정합니다. 마이그레이션은 같은 이미지로 돌립니다: `docker run --rm --env-file .env jkymhs-ai alembic upgrade head`.
