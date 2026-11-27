# 어디갈래 AI 파트 TRD

| 항목 | 내용 |
|---|---|
| 버전 | v0.2 (초안) |
| 작성일 | 2026-11-26 |
| 범위 | AI 서버: `POST /v1/courses`, 장소 정보 보강 배치, 기록·평가 |
| 기준 | Spring 추천 구현 `JKYMHS/JKYMHS-Backend` `develop` (운영 배포 2026-11-18). 계약 원본은 `domain/recommendation/client/ai/AiCourseRequest.java`, `AiCourseResponse.java` |
| 함께 볼 문서 | [`PRD.md`](PRD.md), [`DB.md`](DB.md), [`TASKS.md`](TASKS.md) |

> 표기: **[확정]** 결정됨 · **[미결]** 결정 대기 · **[제안]** 구현 전 확인 · **[건의]** Spring에 요청할 사항
>
> 계약이 이 문서와 Spring 코드에서 다르면 **Spring 코드가 기준**입니다. 계약을 바꾸려면 Spring 담당과 먼저 합의합니다.

---

## 1. 아키텍처

### 1.1 전체 구조

```
                         115 인스턴스 (한 대)
┌──────┐ HTTPS ┌──────────────────────────────────────────────┐  localhost   ┌───────────────────────────┐
│  FE  │──────▶│ Spring Boot 4.1.1 (Java 21)                    │─────────────▶│ AI 서버 (FastAPI)           │
│      │◀ poll─│ 접수·횟수 → 후보 → [AI 호출] → 검증·재요청       │  POST        │ POST /v1/courses           │
└──────┘       │ → 기본 코스 → 시각·경로·식사 → Redis 결과 24h    │  /v1/courses │ 보강 정보 조회 → Gemini      │
               │ 추천 실행기 4–8, 대기열 50, 작업 제한 25초        │  Bearer      │ → 자체 점검·보정 → 응답       │
               └───────────────┬──────────────────────────────┘              │ 배치: 설명문·태그·임베딩       │
                               │                                              └──────┬──────────────┬─────┘
                               ▼                                                     │              ▼
            ┌───────────── MySQL 8 (jkymhs, ai) · Redis ──────────────┐◀──────────────┘          Gemini
            │ jkymhs: Spring 소유. AI는 콘텐츠 view만 읽음 (DB.md)        │   ai 스키마 읽기·쓰기    (결제 계정)
            └──────────────────────────────────────────────────────┘
```

### 1.2 담당 [확정]

| 구성 요소 | 하는 일 | 하지 않는 일 |
|---|---|---|
| Spring | 요청 접수, 횟수, 진행 상태, 후보 고르기, AI 호출, 검증과 1회 재요청, 기본 추천 코스, 시각·경로·식사 칸, 결과 보관(Redis), 일정 저장 | 코스 구성 |
| AI 서버 | 코스 구성(`POST /v1/courses`), 응답 전 자체 점검·보정, 장소 정보 보강 배치, 호출 기록 | 후보 고르기, 최종 검증, 기본 코스, 경로, 결과 보관, 사용자 데이터 조회 |

### 1.3 기술 스택

| 구분 | 선택 | 상태 |
|---|---|---|
| 언어·서버 | Python 3.12, FastAPI, Uvicorn, `asyncio` | [확정] |
| 오케스트레이션 | 프레임워크 없음(LangGraph·LangChain 쓰지 않음). 일반 async 코드 | [확정] |
| LLM SDK | `google-genai` (비동기 클라이언트) | [확정] |
| LLM | Gemini 2.5 Flash. 모델 ID는 설정값 | [확정] · 호출 가능 여부 확인 필요 |
| 임베딩 | Gemini 임베딩 모델. 개인화·재정렬을 쓸 때만 | [미결] |
| DB | SQLAlchemy 2.x(async) + `asyncmy`, 마이그레이션 Alembic(`ai` 스키마만) | [제안] |
| 배포 | Docker, 115 인스턴스 안. Spring이 localhost로 호출 | [제안] Spring 담당과 확정 필요 |

---

## 2. DB

DB 설계의 기준은 [`DB.md`](DB.md)입니다. 요약:

| 항목 | 규칙 |
|---|---|
| `jkymhs`(Spring) | AI는 쓰지 않습니다. 배치는 콘텐츠 view(`ai_content_source`)만 읽습니다 [건의]. view가 생기기 전에는 콘텐츠 테이블 SELECT 권한으로 대신합니다 |
| 사용자 데이터 | 요청 본문으로만 받습니다. 사용자 테이블은 읽지 않습니다 |
| `ai` 스키마 | `place_profiles`, `place_embeddings`, `course_outputs`, `ai_call_logs`, `ai_call_daily_stats`, `batch_watermarks`, `batch_runs` |

---

## 3. 계약: `POST /v1/courses`

### 3.1 공통

| 항목 | 값 | 출처 |
|---|---|---|
| 주소 | `{AI_BASE_URL}/v1/courses` (예: `http://localhost:8000`) | `HttpAiCourseClient` |
| 인증 | `Authorization: Bearer {AI_API_KEY}`. 키가 다르면 401 | `HttpAiCourseClient` |
| 형식 | `application/json` 요청·응답. 시각 `"HH:mm"`, 날짜 `"YYYY-MM-DD"` | `AiCourseRequest` |
| Spring 대기 한도 | 20초(`ai.timeout`). 넘으면 기본 추천 코스 | `application.yml` |
| Spring 작업 전체 한도 | 25초(`recommendation.deadline`). 넘으면 재요청과 외부 경로 조회를 건너뜀 | `application.yml` |
| 재요청 | 검증 위반이 있으면 `violations`를 채워 1회 다시 호출 | `RecommendationWorker` |
| 오류 응답 | 4xx·5xx·형식 오류는 모두 Spring이 기본 추천 코스로 대신함. 사용자는 실패 화면을 보지 않음 | `HttpAiCourseClient` |

### 3.2 요청

```json
{
  "requestId": 123,
  "conditions": {
    "startDate": "2026-12-20", "endDate": "2026-12-21", "startTime": "10:00",
    "companion": "kids",              // alone·couple·friends·kids·parents
    "childAgeGroup": "ELEMENTARY",    // INFANT·ELEMENTARY·TEEN 또는 null
    "pace": "relaxed",                // relaxed·packed
    "indoor": false,
    "timeOfDay": "morning",           // early·morning·afternoon. 둘째 날부터의 시작 시간대
    "origin": {"lat": 37.5701, "lng": 126.9832}   // 첫날 출발지
  },
  "profile": { "topCategories": [ {"lcls2": "VE01", "score": 0.82} ] },   // 최대 5개. 신호 없으면 빈 배열
  "candidates": [
    { "contentId": 126508, "name": "국립민속박물관", "lat": 37.5817, "lng": 126.9791,
      "category": "박물관", "io": "INDOOR",
      "openTime": "09:00", "closeTime": "18:00", "lastEntryTime": "17:00",
      "restDays": ["MON"],            // 빈 배열 = 쉬는 날 없음, null = 모름
      "eventStartDate": null, "eventEndDate": null,   // 축제일 때만
      "required": false }
  ],
  "rules": {
    "courses": 3,
    "placesPerDay": {"min": 1, "max": 2},   // 여유 2–3·알참 4–5, 아이 동반이면 하나씩 줄임
    "lunch": "11:30-13:30", "dinner": "17:30-19:30",
    "noPlaceAfter": "20:00"           // 아이 동반일 때만, 아니면 null
  },
  "violations": []                    // 재요청일 때만 채워짐 (한국어 문장)
}
```

- `candidates`는 Spring 점수 높은 순 최대 40곳 + 꼭 포함 장소입니다. 축제는 `openTime`·`closeTime`에 행사 시작·종료 시각이 들어옵니다.
- `origin`은 거리 계산에만 씁니다. LLM 프롬프트에 넣지 않고, 저장하거나 로그에 남기지 않습니다.

### 3.3 응답

```json
{
  "courses": [
    { "title": "인기 명소 코스",
      "summary": "아이와 함께 실내 전시 중심으로 둘러보는 코스",
      "days": [
        { "dayNumber": 1,
          "items": [ {"contentId": 126508, "stayMinutes": 90, "reason": "아이와 체험하기 좋은 실내 전시"} ] }
      ] }
  ]
}
```
- `stayMinutes`가 비었거나 이상하면 Spring이 90분으로 바꿉니다.
- 식사 칸, 시각, 이동은 응답에 넣지 않습니다. Spring이 붙입니다.

### 3.4 Spring 검증 규칙 (`CourseValidator`)

AI 서버의 자체 점검(5.4)은 이 규칙을 그대로 따릅니다.

| # | 규칙 | 위반 문장 예 |
|---|---|---|
| 1 | 코스 수 = `rules.courses` | "코스는 3개가 필요합니다." |
| 2 | 각 코스에 `days`가 있고 `dayNumber` 1–N이 하루씩 | "코스 1: dayNumber는 1~2이 한 번씩 있어야 합니다." |
| 3 | 하루 장소 수가 `placesPerDay` 범위 | "코스 2: 2일차 장소는 2~3곳이어야 합니다 (4곳)." |
| 4 | 후보에 있는 장소만 | "코스 1: 후보에 없는 장소입니다: 999" |
| 5 | 한 코스 안에서 중복 없음 | "코스 1: 같은 장소가 두 번 들어갔습니다: 126508" |
| 6 | 꼭 포함 장소가 모든 코스에 | "코스 3: 꼭 포함할 장소가 빠졌습니다: 264337" |
| 7 | 축제는 기간 안의 날에만 | "코스 1: 축제 2830는 2026-12-21에 열리지 않습니다." |
| 8 | 쉬는 요일에 넣지 않음 | "코스 2: 126508는 2026-12-21(MONDAY)에 쉽니다." |
| 9 | 아이 동반이면 20:00 전에 끝남 | "코스 1: 아이와 가는 일정은 20:00 전에 끝나야 합니다: …" |
| 10 | 방문 시각이 영업시간 안. 시각은 Spring 경로 추정(`RouteService.estimate`)으로 계산 | "코스 1: 126508 방문 시각 17:40~19:10이 영업시간 09:00~18:00 밖입니다." |

꼭 포함 장소는 7·8·10번 검사에서 빠집니다.

### 3.5 계약 건의 [건의]

| # | 건의 | 이유 |
|---|---|---|
| 1 | `conditions.accessibleOnly` 추가 | 이동 편의 토글이 지금 추천에 쓰이지 않음 |
| 2 | `reason` 최대 40자 명시 | 응답 크기·지연 감소 |
| 3 | 코스 1–3개 응답 허용 (규칙 1 완화) | 일부 코스만 실패해도 전체가 기본 코스로 바뀌지 않게 |
| 4 | 시각 계산 방식 공유: `RouteService.estimate`의 식, 첫날 출발·둘째 날 시작 시각, 식사 칸이 시간표에 들어가는 방식 | AI 자체 점검이 Spring과 같은 시각을 계산해야 규칙 10을 미리 지킬 수 있음 |
| 5 | (결정 3) `profile.recentContentIds` | 임베딩 기반 개인화 |
| 6 | (나중에) `POST /v1/candidates/rank` | 인기 점수가 0인 동안 후보 풀 재정렬 |

---

## 4. AI 서버의 다른 API

| API | 용도 |
|---|---|
| `GET /health` | 프로세스 상태, DB 연결, Gemini 설정 확인. 인증 없음, localhost 전용 |

---

## 5. 코스 구성 파이프라인

### 5.1 흐름

```python
async def compose_courses(req: AiCourseRequest) -> AiCourseResponse:
    deadline = now() + 18s                                    # Spring 대기 한도 20초보다 먼저 응답
    places = await enrich(req.candidates)                     # ai.place_profiles를 contentId로 조회
    themes = ["popular", "relaxed", "hidden"]                 # 코스 1·2·3의 성격 (PRD 3.4)
    drafts = await gather_with_deadline(                      # 코스 3개를 동시에 생성
        [compose_one(req, places, t) for t in themes], timeout=12s)
    drafts = await retry_missing(drafts, req, places, deadline)   # 실패한 코스만, 시간이 남으면 1회
    if any(d is None for d in drafts):
        raise ComposeFailed                                   # 503 → Spring이 기본 코스
    courses = [repair(d, req) for d in drafts]                # 자체 점검·보정 (5.4)
    courses = diversify(courses, req)                         # 코스 사이 겹침 줄이기 (5.5)
    courses = sanitize_reasons(courses, places)               # 추천 이유 검사 (5.6)
    record_output(req, courses)                               # ai.course_outputs, ai_call_logs
    return AiCourseResponse(courses=courses)
```

### 5.2 보강 정보 (`enrich`)
- `ai.place_profiles`를 `contentId` 목록으로 한 번에 조회합니다(최대 41건).
- 보강 정보가 없는 장소는 요청의 이름·분류·실내 여부만 씁니다.
- 결과는 프로세스 메모리에 캐시합니다(배치가 끝나면 무효화).

### 5.3 LLM 호출 (`compose_one`)

| 항목 | 값 |
|---|---|
| 모델 | 설정값 `GEMINI_COMPOSE_MODEL` (기본 `gemini-2.5-flash`) |
| `thinking_budget` | 0으로 시작, 평가 결과에 따라 512·1024 비교 |
| 구조화 출력 | `response_mime_type="application/json"`, `response_schema` = 코스 1개 스키마 |
| `max_output_tokens` | 1,024 (3박 4일 × 5곳 기준으로 측정 후 조정) |
| 타임아웃 | 호출당 12초 |
| 동시 호출 | 요청당 3개, 서버 전체는 세마포어로 24개(Spring 실행기 8 × 3) |
| 프롬프트 | 고정 부분(역할, 규칙, 출력 형식, 예시)을 앞에, 바뀌는 부분(조건, 후보, 위반 목록)을 뒤에. 암묵적 캐싱 대상 |
| 재요청 | `violations`가 있으면 "직전 응답이 어긴 규칙" 절로 넣음 |

**후보 입력 형식** (토큰을 줄이기 위해 한 줄씩)
```
id|이름|분류|실내|영업|쉬는요일|축제기간|필수|태그|권장체류|출발지순위|묶음
126508|국립민속박물관|박물관|INDOOR|09:00-18:00(입장17:00)|MON|-|N|교육적,어린이체험|60-120|3|A
```
- 좌표 대신 **서버가 미리 계산한 거리 정보**를 넣습니다: 출발지에서 가까운 순위, 가까운 장소끼리 묶은 묶음 기호. LLM이 직접 거리를 계산하지 않게 합니다.
- 사용자 ID, 출발지 좌표는 넣지 않습니다.

**코스 1개 출력 스키마**
```json
{"title": "string", "summary": "string",
 "days": [{"dayNumber": 1, "items": [{"contentId": 0, "stayMinutes": 0, "reason": "string"}]}]}
```

### 5.4 자체 점검과 보정 (`repair`)

3.4의 규칙 1–9를 그대로 검사하고, 규칙 10은 근사 시각으로 검사합니다(3.5 건의 4가 받아들여지면 Spring과 같은 식으로 바꿈).

| 위반 | 보정 |
|---|---|
| 후보에 없는 장소, 중복 | 제거 |
| 꼭 포함 누락 | 가장 가까운 일차의 이동이 가장 적게 늘어나는 위치에 삽입 |
| 하루 장소 수 초과 | 꼭 포함이 아닌 장소 중 점수가 낮은 것을 다른 날로 옮기거나 제거 |
| 하루 장소 수 부족 | 그날 장소와 가까운 후보 중 다른 날에 없는 것을 추가 |
| 쉬는 요일, 축제 기간 밖 | 다른 날로 옮기고, 안 되면 비슷한 후보로 교체 |
| 영업시간 밖(근사) | 체류 시간 단축 → 같은 날 순서 교체 → 교체 |
| 아이 동반 20시 초과 | 마지막 장소 제거 또는 체류 시간 단축 |

보정해도 위반이 남으면 그대로 돌려줍니다. Spring이 위반 목록으로 재요청합니다.

### 5.5 코스 사이 겹침 (`diversify`)
꼭 포함 장소를 뺀 장소가 두 코스 사이에서 50% 넘게 겹치면, 뒤 코스의 겹친 장소를 그 코스의 성격에 맞는 다른 후보로 바꿉니다. 바꾼 뒤 5.4를 다시 돌립니다.

### 5.6 추천 이유 검사 (`sanitize_reasons`)
- 40자를 넘거나, 금지 표현(설정 파일: `무료`, `할인`, `원`, `주차`, `예약`, `시까지`, `시부터`, `최고의` 등)이 있으면 그 장소만 기본 문장으로 바꿉니다.
- 바꾼 수는 `ai_call_logs.violations_json`에 남깁니다.

### 5.7 시간 예산

| 단계 | 목표 | 상한 |
|---|---|---|
| 요청 검증·보강 조회 | 0.1초 | 0.5초 |
| LLM 3개 동시 호출 | 4–7초 | 12초 |
| 실패 코스 재생성(필요할 때만) | – | 남은 시간 안에서 |
| 자체 점검·보정·겹침·이유 | 0.1초 | 0.5초 |
| **합계** | **약 5–8초** | **18초** |

Spring 쪽에서는 첫 호출과 재요청을 합쳐 25초 안에 들어와야 하므로, 첫 호출이 10초 안에 끝나야 재요청 여유가 생깁니다.

### 5.8 프롬프트 관리
- 프롬프트는 `prompts/` 폴더에 버전을 붙인 파일로 둡니다(예: `compose.v1.txt`).
- 쓰는 버전은 설정값(`PROMPT_COMPOSE_VERSION`)으로 고르고 `ai_call_logs.prompt_version`에 남깁니다.
- 바꾸면 회귀 평가(9장)를 돌리고, 통과율과 응답 시간이 나빠지지 않을 때만 배포합니다.

---

## 6. 오류 처리

| 상황 | AI 서버 응답 | Spring 처리 |
|---|---|---|
| 인증 키 없음·불일치 | 401 | 기본 추천 코스 |
| 요청 형식 오류 | 422 `{"code": "INVALID_REQUEST"}` | 기본 추천 코스 |
| 후보가 없음 | 422 `{"code": "NO_CANDIDATES"}` | 기본 추천 코스 (Spring이 먼저 걸러서 정상 흐름에서는 없음) |
| Gemini 시간 초과·오류·한도 초과로 코스를 다 못 만듦 | 503 `{"code": "LLM_UNAVAILABLE"}` | 기본 추천 코스 |
| 18초 초과 | 503 `{"code": "DEADLINE"}` | 기본 추천 코스 |
| 그 밖의 오류 | 500 | 기본 추천 코스 |

오류 본문에 내부 정보를 넣지 않습니다. 모든 요청의 `requestId`를 로그로 남깁니다.

---

## 7. 장소 정보 보강 배치

### 7.1 흐름

```
[Spring] TourAPI 동기화 (TOUR_SYNC, 소개 정보 30일마다 재수신)
            │
[AI] 매일 새벽, batch_watermarks 이후로 바뀐 콘텐츠만
   ① 대상: content_type이 ATTRACTION·FESTIVAL, is_deleted = 0
   ② 변경 감지: tour_modified_at, intro_fetched_at, content_details.fetched_at 중 가장 늦은 시각 > 워터마크
               + 원문 해시(source_hash)가 바뀐 것만
   ③ 설명문·태그·권장 체류 시간 생성 (Gemini Batch API) → place_profiles
   ④ (개인화·재정렬을 쓸 때) 임베딩 → place_embeddings
   ⑤ 워터마크 갱신, batch_runs 기록
```
`contents.updated_at`은 동기화 때마다, `intro_fetched_at`은 30일마다 내용이 같아도 갱신됩니다. 그래서 시각은 후보를 고르는 데만 쓰고, 실제로 다시 만들지는 원문 해시로 정합니다. 30일마다 대상 대부분이 후보로 잡히지만, 해시 비교는 DB 조회만 하므로 LLM 비용은 들지 않습니다.

### 7.2 설명문 형식
```
[장소] {이름} / {시·군·구} / {대분류} > {소분류}
[분위기] ...  [활동] ...
[적합 동행] ...
[실내] 예|아니오|혼합  [소요] N–M시간
```
- 원문: 이름, 분류(`lcls1`–`lcls3`, `tour_classifications.name`), `io_type`, `pet_allowed`, `content_details.overview`, `fee`, `age_limit`, `event_program`.
- 원문은 프롬프트의 데이터 영역(`<source>` … `</source>`)에만 넣고, 그 안의 지시는 따르지 않게 합니다.
- 근거가 없는 항목은 "정보 없음". 개요가 없으면 이름과 분류만으로 짧게 만듭니다.

### 7.3 운영

| 항목 | 규칙 |
|---|---|
| 실행 시각 | 새벽 3–5시 |
| 처리량 | 처음 1회는 대상 지역 전체(종로구로 PoC), 이후 변경분만 |
| 재시도 | 실패한 콘텐츠만 다음 실행에서 |
| 측정 | 생성 성공률, 개요 없는 장소 비율, 태그 분포 |

---

## 8. 보안과 개인정보

| 항목 | 규칙 |
|---|---|
| 서버 간 인증 | `Authorization: Bearer {AI_API_KEY}`. localhost에서만 받음 |
| DB 권한 | `ai` 스키마 전체, `jkymhs`는 콘텐츠 view(또는 콘텐츠 테이블) SELECT만 (DB.md 6) |
| LLM 계정 | 결제 계정이 연결된 Cloud 프로젝트로만 호출 |
| LLM에 보내지 않는 것 | 사용자 식별 정보, 출발지 좌표 |
| 출발지 좌표 | 메모리에서 거리 계산에만 씀. 저장·로그 금지 |
| 기록 | 프롬프트·응답 원문은 저장하지 않음. `course_outputs`에는 장소 ID·순서·체류 시간만 |
| 비밀값 | 환경 변수로 주입. 저장소에 넣지 않음 |

---

## 9. 테스트와 평가

| 종류 | 내용 |
|---|---|
| 단위 테스트 | 자체 점검 규칙 1–10, 보정, 겹침 줄이기, 추천 이유 검사, 후보 입력 형식 |
| 계약 테스트 | Spring의 `AiCourseRequest`·`AiCourseResponse` 예시 JSON으로 요청·응답 왕복. Spring 저장소의 계약이 바뀌면 실패하게 함 |
| 평가셋 | 운영 DB 콘텐츠로 만든 요청 수백 건(지역·기간·동행·페이스·꼭 포함 조합). Spring `CourseValidator` 규칙을 그대로 옮긴 검사기로 채점 |
| 지표 | 첫 응답 검증 통과율, 보정 비율, 코스 사이 겹침, 추천 이유 대체율, p50·p95 응답 시간, 토큰 |
| 회귀 | 프롬프트·모델·설정을 바꿀 때마다 같은 평가셋으로 비교 |
| 부하 | 동시 8건(Spring 실행기 최대)에서 p95 |

---

## 10. 배포, 운영, 관측

| 항목 | 내용 |
|---|---|
| 배포 | Docker 이미지 하나(API와 배치 공용). 115 인스턴스에서 실행, Spring은 `AI_BASE_URL=http://localhost:8000` |
| 프로세스 | Uvicorn 워커 2개 [제안]. 같은 서버에 Spring, MySQL, Redis가 있으므로 메모리 확인 |
| Gemini 한도 | 결제 계정의 분당 요청·토큰 한도가 동시 24호출을 감당하는지 확인. 429면 해당 코스 실패로 처리 |
| 예산 | 월 예산 80%에 알림 |
| 추적 | `requestId`를 모든 로그와 `ai_call_logs`에 기록 |
| 지표 | 단계별 지연, 실패율, 첫 응답 통과율(Spring 재요청 비율), 토큰·비용 |
| 알림 | 오류율 5% 초과, p95 12초 초과, 예산 80% |
| 보관 | `ai_call_logs`·`course_outputs` 90일, 일별 집계 계속 |

---

## 11. 설정값

| 키 | 기본값 |
|---|---|
| `AI_API_KEY` | (비밀값) |
| `GEMINI_COMPOSE_MODEL` / `GEMINI_BATCH_MODEL` | `gemini-2.5-flash` |
| `GEMINI_EMBED_MODEL` | (확인 필요) |
| `COMPOSE_DEADLINE_SEC` | 18 |
| `COMPOSE_CALL_TIMEOUT_SEC` | 12 |
| `COMPOSE_THINKING_BUDGET` | 0 |
| `COMPOSE_MAX_OUTPUT_TOKENS` | 1024 |
| `LLM_CONCURRENCY` | 24 |
| `COURSE_OVERLAP_MAX` | 0.5 |
| `REASON_MAX_CHARS` | 40 |
| `PROMPT_COMPOSE_VERSION` | 최신 검증 버전 |
| `UVICORN_WORKERS` | 2 |
| `GEMINI_MONTHLY_BUDGET_USD` | (팀 결정) |

코스 성격 설명, 금지 표현, 기본 문장 템플릿은 코드가 아닌 설정 파일에 둡니다.

---

## 12. 개발 순서

작업 순서와 완료 기준은 [`TASKS.md`](TASKS.md)에서 관리합니다.

---

## 13. 미결 사항

| # | 항목 | 영향 |
|---|---|---|
| 1 | 코스 구성 방식(LLM 중심 / 최적화 엔진 + LLM 이유) | 5.3–5.5 |
| 2 | 개인화 방식(임베딩 사용 여부), 계약 건의 5 | 7.1 ④, 3.5 |
| 3 | Gemini 2.5 Flash 호출 가능 여부, 임베딩 모델 ID | 11 |
| 4 | 계약 건의(3.5) 수용 여부, 특히 4번(시각 계산 방식 공유) | 5.4 |
| 5 | AI 배치용 view 제공 여부 | 2, DB.md |
| 6 | 115 인스턴스 배포 확정과 사양(RAM) | 10 |
| 7 | 상세 정보 수집 범위 | 7.2 |
| 8 | LLM 월 예산 | 10 |
