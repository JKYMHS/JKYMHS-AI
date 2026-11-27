# 어디갈래 AI 파트 DB 설계

| 항목 | 내용 |
|---|---|
| 버전 | v0.2 (초안) |
| 작성일 | 2026-11-26 |
| 기준 | 운영 DB `jkymhs`의 실제 구조(MySQL 8, 31개 테이블, 2026-11-26), Spring 담당 답변(2026-11-26) |
| 함께 볼 문서 | [`TRD.md`](TRD.md), [`PRD.md`](PRD.md) |

> 표기: **[확정]** 결정됨 · **[제안]** 구현 전 확인 · **[건의]** 백엔드에 요청할 사항 · **[미결]** 결정 대기
>
> 이 문서가 DB에 관한 기준입니다.

---

## 1. 개요

```
MySQL 인스턴스 하나 (115)
├ jkymhs 스키마   Spring 소유 (31개 테이블). 스키마는 ddl-auto: update로 관리됨
│   └ AI 계정: 콘텐츠 view(ai_content_source) SELECT만 [건의]
│              view가 생기기 전에는 콘텐츠 테이블 4개 SELECT로 대신 (6장)
└ ai 스키마       AI 서버 소유 (Alembic) → AI 계정: 전체 권한
```

**원칙** [확정]
- AI 서버는 `jkymhs`에 쓰지 않습니다.
- AI 서버가 `jkymhs`에서 읽는 것은 **장소 정보 보강 배치에 필요한 콘텐츠 데이터뿐**입니다. 코스 구성 요청을 처리할 때는 DB의 `jkymhs`를 읽지 않습니다. 필요한 값은 Spring이 요청 본문(`AiCourseRequest`)에 담아 보냅니다.
- 사용자 데이터(취향, 행동, 요청 조건)는 요청 본문으로만 받습니다.
- `ai` 테이블은 `jkymhs.contents.id`(= TourAPI `contentid`, BIGINT)를 외래 키 없이 값으로 참조합니다. 스키마를 넘는 외래 키는 두 서버의 스키마 변경을 묶기 때문입니다.
- 추천 결과와 진행 상태는 Spring이 Redis에 24시간 보관합니다. AI 서버는 결과를 DB에 보관하지 않고, 품질 측정용 요약만 남깁니다(3.3).

---

## 2. `jkymhs`에서 AI가 쓰는 것

### 2.1 배치가 읽는 열

| 테이블 | 열 | 용도 |
|---|---|---|
| `contents` (31,702행) | `id`, `name`, `content_type`, `is_deleted`, `lcls1`–`lcls3`, `region_id`, `io_type`, `pet_allowed`, `tour_modified_at`, `intro_fetched_at` | 설명문 원문, 대상 선택, 변경 감지 |
| `content_details` (6,518행) | `content_id`, `overview`, `fee`, `age_limit`, `event_program`, `fetched_at` | 설명문 원문 |
| `tour_classifications` (315행) | `code`, `name` | 분류 이름 |
| `regions` (284행) | `id`, `name` | 시·군·구 이름 |

**변경 감지**: `GREATEST(tour_modified_at, intro_fetched_at, content_details.fetched_at)`로 후보를 고르고, **원문 해시(`source_hash`)가 바뀐 것만** 다시 만듭니다. `contents.updated_at`은 동기화 때마다, `intro_fetched_at`은 30일마다 내용이 같아도 갱신되므로 시각만으로는 변경을 알 수 없습니다.

**알아 둘 점** (Spring 답변 기준)
- `contents.id`는 TourAPI `contentid` 그대로입니다(자동 증가 아님). `content_images`는 상세를 갱신할 때 지우고 다시 넣어 id가 바뀝니다. AI는 이 테이블을 쓰지 않습니다.
- 콘텐츠 행은 지우지 않습니다. TourAPI에서 내려가면 `is_deleted = 1`, 다시 보이면 0입니다.
- `io_type`은 소분류(`lcls3`) 단위 값입니다(`tour_classifications.io_type`).
- `content_details`는 장소의 약 20%만 채워져 있습니다. 수집 범위는 확인 중입니다 [미결].

### 2.2 요청 본문으로 받는 것 (읽지 않음)

`AiCourseRequest`에 담겨 오는 값입니다(TRD 3.2). 출처는 참고용입니다.

| 요청 필드 | 출처 (Spring) |
|---|---|
| `conditions.*` | `recommendation_requests`, `user_preferences` |
| `conditions.origin` | `recommendation_requests.origin_lat`, `origin_lng` (24시간 뒤 Spring이 지움) |
| `profile.topCategories` | `preference_profiles` (`profile_key` = 동행 코드 소문자 또는 `common`) |
| `candidates[]` | `contents` + Spring 후보 점수 |
| `candidates[].required` | `recommendation_required_places` |

### 2.3 접근하지 않는 테이블

회원·인증(`users`, `refresh_tokens`, `user_consents`, `user_preferences`, `user_travel_styles`), 여행·일정(`trips`, `trip_regions`, `plans`, `plan_items`, `visit_reviews`), 추천(`recommendation_*`, `preference_profiles`), 행동(`behavior_events`, `content_views`, `content_save_logs`, `wishlists`), 캘린더, 배치(`batch_job_logs`, `tour_sync_cursors`), `categories`, `category_mappings`, `travel_style_mappings`, `content_images`.

---

## 3. `ai` 스키마

```sql
CREATE DATABASE ai CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```
모든 시각은 `DATETIME(6)`(KST)입니다.

### 3.1 `place_profiles`: 장소 보강 정보

```sql
CREATE TABLE place_profiles (
  content_id        BIGINT       NOT NULL PRIMARY KEY,   -- jkymhs.contents.id
  description       TEXT         NOT NULL,               -- 정해진 틀의 설명문 (TRD 7.2)
  tags_json         JSON         NOT NULL,               -- 아래 형식
  min_stay_min      SMALLINT     NOT NULL,
  typical_stay_min  SMALLINT     NOT NULL,
  has_overview      BOOLEAN      NOT NULL,               -- 원문 개요가 있었는지 (품질 측정)
  source_hash       CHAR(64)     NOT NULL,               -- 원문 해시. 같으면 다시 만들지 않음
  source_changed_at DATETIME(6)  NOT NULL,               -- 만들 때 본 원문 변경 시각
  model             VARCHAR(60)  NOT NULL,
  prompt_version    VARCHAR(20)  NOT NULL,
  updated_at        DATETIME(6)  NOT NULL
);
```

**`tags_json` 형식**
```json
{
  "mood":       ["조용함", "교육적"],
  "activity":   ["전시 관람", "어린이 체험"],
  "companion":  {"kids": true, "parents": true, "couple": null},   // null = 판단 불가
  "accessible": true                                                // 휠체어·유모차 이용 가능. null = 정보 없음
}
```
실내 여부와 반려동물은 Spring 값(`io_type`, `pet_allowed`)이 기준이라 태그에 넣지 않습니다.

### 3.2 `place_embeddings`: 장소 임베딩 [미결: 결정 3]

```sql
CREATE TABLE place_embeddings (
  content_id   BIGINT       NOT NULL,
  model        VARCHAR(60)  NOT NULL,
  dim          SMALLINT     NOT NULL,                    -- 기본 768
  vector       BLOB         NOT NULL,                    -- float32 little-endian
  source_hash  CHAR(64)     NOT NULL,                    -- place_profiles.source_hash와 같으면 재계산 생략
  updated_at   DATETIME(6)  NOT NULL,
  PRIMARY KEY (content_id, model)
);
```
임베딩 기반 개인화나 후보 재정렬을 하기로 정한 뒤에 만듭니다.

### 3.3 `course_outputs`: 코스 구성 결과 요약

```sql
CREATE TABLE course_outputs (
  id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  request_id      BIGINT       NOT NULL,                 -- jkymhs.recommendation_requests.id
  attempt         TINYINT      NOT NULL,                 -- 1 = 첫 호출, 2 = 위반 목록 재요청
  courses_json    JSON         NOT NULL,                 -- 코스별 [일차, contentId, stayMinutes]. 추천 이유·제목은 넣지 않음
  self_violations JSON         NULL,                     -- 자체 점검에서 보정한 위반
  remaining_violations JSON    NULL,                     -- 보정 후에도 남은 위반
  overlap_max     DECIMAL(4,3) NOT NULL,                 -- 코스 사이 최대 겹침
  candidate_count SMALLINT     NOT NULL,
  latency_ms      INT          NOT NULL,
  created_at      DATETIME(6)  NOT NULL,
  INDEX (request_id), INDEX (created_at)
);
```
- Spring 재요청 비율(= `attempt = 2`인 비율)이 "첫 응답 검증 통과율"의 실측값입니다.
- 사용자 정보와 출발지는 넣지 않습니다. **90일 보관**.

### 3.4 `ai_call_logs`: LLM 호출 기록

```sql
CREATE TABLE ai_call_logs (
  id               BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  request_id       BIGINT       NULL,                    -- 배치 호출은 NULL
  purpose          ENUM('COMPOSE','PROFILE','EMBED') NOT NULL,
  course_theme     VARCHAR(20)  NULL,                    -- popular·relaxed·hidden (COMPOSE만)
  model            VARCHAR(60)  NOT NULL,
  prompt_version   VARCHAR(20)  NOT NULL,
  thinking_budget  INT          NULL,
  is_batch         BOOLEAN      NOT NULL DEFAULT FALSE,
  prompt_tokens    INT          NULL,
  output_tokens    INT          NULL,
  thoughts_tokens  INT          NULL,
  cached_tokens    INT          NULL,
  finish_reason    VARCHAR(30)  NULL,
  latency_ms       INT          NOT NULL,
  outcome          ENUM('OK','REPAIRED','INVALID','TIMEOUT','RATE_LIMITED','ERROR') NOT NULL,
  violations_json  JSON         NULL,                    -- 추천 이유 대체 수 등
  created_at       DATETIME(6)  NOT NULL,
  INDEX (request_id), INDEX (created_at)
);
```
프롬프트와 응답 원문은 저장하지 않습니다. **90일 보관**.

### 3.5 `ai_call_daily_stats`: 일별 집계

```sql
CREATE TABLE ai_call_daily_stats (
  stat_date        DATE         NOT NULL,
  purpose          VARCHAR(20)  NOT NULL,
  model            VARCHAR(60)  NOT NULL,
  calls            INT          NOT NULL,
  errors           INT          NOT NULL,
  prompt_tokens    BIGINT       NOT NULL,
  output_tokens    BIGINT       NOT NULL,
  thoughts_tokens  BIGINT       NOT NULL,
  cached_tokens    BIGINT       NOT NULL,
  cost_usd         DECIMAL(10,4) NOT NULL,
  latency_p50_ms   INT          NOT NULL,
  latency_p95_ms   INT          NOT NULL,
  first_pass_rate  DECIMAL(4,3) NULL,                    -- COMPOSE만: course_outputs 기준 재요청 없이 끝난 비율
  PRIMARY KEY (stat_date, purpose, model)
);
```
매일 새벽 전날 분을 집계합니다. 계속 보관합니다.

### 3.6 `batch_watermarks`: 배치 진행 위치

```sql
CREATE TABLE batch_watermarks (
  job              VARCHAR(40)  NOT NULL PRIMARY KEY,    -- 'profile', 'embed'
  last_changed_at  DATETIME(6)  NOT NULL,
  last_content_id  BIGINT       NOT NULL DEFAULT 0,      -- 같은 시각 안에서 이어서 처리
  updated_at       DATETIME(6)  NOT NULL
);
```

### 3.7 `batch_runs`: 배치 실행 기록

```sql
CREATE TABLE batch_runs (
  id               BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  job              VARCHAR(40)  NOT NULL,
  status           ENUM('RUNNING','SUCCESS','PARTIAL','FAILED') NOT NULL,   -- jkymhs.batch_job_logs와 같은 값
  started_at       DATETIME(6)  NOT NULL,
  finished_at      DATETIME(6)  NULL,
  processed_count  INT          NOT NULL DEFAULT 0,
  failed_count     INT          NOT NULL DEFAULT 0,
  api_call_count   INT          NOT NULL DEFAULT 0,
  error_message    VARCHAR(1000) NULL,
  INDEX (job, started_at)
);
```

### 3.8 정리 작업

| 작업 | 주기 | 내용 |
|---|---|---|
| 기록 삭제 | 매일 | `ai_call_logs`, `course_outputs`에서 90일 지난 행 |
| 일별 집계 | 매일 | 전날 분을 `ai_call_daily_stats`로 |
| 고아 행 정리 | 매주 | `jkymhs.contents`에 없는 `content_id`의 `place_profiles`, `place_embeddings`. `is_deleted = 1`은 다시 보일 수 있으므로 지우지 않음 |

---

## 4. 관계도

```
 jkymhs (Spring, 읽기 전용, 배치만)              ai (AI 서버)
┌──────────────────────────────┐   content_id  ┌──────────────────────────┐
│ contents ─▶ content_details   │──(값 참조)──▶│ place_profiles            │
│ tour_classifications, regions │               │ place_embeddings          │
└──────────────────────────────┘               └──────────────────────────┘
 Spring 요청 본문의 requestId ──(값 참조)──────▶ course_outputs, ai_call_logs ─▶ ai_call_daily_stats
                                                 batch_watermarks, batch_runs
```

---

## 5. `jkymhs` 관련 건의 [건의]

### 5.1 AI 배치용 view

테이블에 직접 권한을 주면 AI 코드가 Spring 테이블 구조에 묶입니다(Spring 답변 B6). 게다가 스키마를 `ddl-auto: update`로 관리하고 있어, 엔티티 필드 이름을 바꾸면 새 열이 생기고 옛 열이 조용히 남습니다. AI가 옛 열을 읽으면 오류 없이 오래된 값을 받게 됩니다. 그래서 읽을 열을 view 하나로 고정해 두 서버 사이의 약속으로 삼습니다.

```sql
CREATE SQL SECURITY DEFINER VIEW jkymhs.ai_content_source AS
SELECT c.id AS content_id, c.name, c.content_type, c.is_deleted,
       c.lcls1, c.lcls2, c.lcls3, tc.name AS lcls3_name, r.name AS region_name,
       c.io_type, c.pet_allowed,
       d.overview, d.fee, d.age_limit, d.event_program,
       GREATEST(COALESCE(c.tour_modified_at, '1970-01-01'), COALESCE(c.intro_fetched_at, '1970-01-01'),
                COALESCE(d.fetched_at, '1970-01-01')) AS changed_at
FROM jkymhs.contents c
LEFT JOIN jkymhs.content_details d ON d.content_id = c.id
LEFT JOIN jkymhs.tour_classifications tc ON tc.code = c.lcls3
LEFT JOIN jkymhs.regions r ON r.id = c.region_id
WHERE c.content_type IN ('ATTRACTION', 'FESTIVAL');
```
Spring이 이 view를 관리하고, 엔티티를 바꿀 때 view도 함께 고칩니다. AI 저장소의 CI에서 view의 열 목록을 확인합니다.

**순서**: `ddl-auto: update`로는 view를 만들거나 고칠 수 없습니다. Spring이 Flyway를 도입한 뒤(5.3 1번) 마이그레이션으로 만듭니다. 그 전에는 6장의 임시 권한(콘텐츠 테이블 4개 SELECT)으로 배치를 돌립니다.

### 5.2 인덱스

```sql
ALTER TABLE jkymhs.contents ADD INDEX idx_ai_changed (tour_modified_at);
```
배치의 변경 감지용입니다. 3만 행 규모라 없어도 동작은 합니다.

### 5.3 그 밖의 건의 (PRD 8.2)

| # | 건의 | 순서 |
|---|---|---|
| 1 | Flyway 도입. 현재 운영 스키마를 baseline으로 | 먼저 |
| 2 | 위치 동의 `LOCATION` CHECK 제약 수정 (운영 CHECK 32개 중 어긋난 유일한 값) | 1번 다음 |
| 3 | `ai_content_source` view (5.1) | 1번 다음 |
| 4 | 후보 풀 동점 정렬: 정보 충실도 → 날짜·`id` 해시 순 (지금은 지역마다 `contentid`가 작은 200곳만 고름) | 바로 |
| 5 | 늦게 시작한 요청 바로 실패 처리, 정리 배치 1분·기준 5분, 대기열 축소 | 바로 |
| 6 | 취향 프로필 가중치에 신뢰도 배수 | 회원이 생기기 전 |
| 7 | Redis 영속 설정 확인 | 바로 |

상세 이유와 계산은 PRD 8.2에 있습니다.

---

## 6. 권한 [건의]

```sql
CREATE USER 'ai_server'@'localhost' IDENTIFIED BY '***';
GRANT ALL PRIVILEGES ON ai.* TO 'ai_server'@'localhost';
GRANT SELECT ON jkymhs.ai_content_source TO 'ai_server'@'localhost';
-- view가 생기기 전 임시:
-- GRANT SELECT ON jkymhs.contents, jkymhs.content_details, jkymhs.tour_classifications, jkymhs.regions ...
ALTER USER 'ai_server'@'localhost' WITH MAX_USER_CONNECTIONS 10;
```
AI 서버가 같은 인스턴스(115)에 있다는 전제입니다. 다른 서버에 두면 호스트를 바꿉니다. `ai` 스키마 마이그레이션은 AI 저장소의 Alembic으로 관리하고, `alembic_version` 테이블도 `ai` 스키마에 둡니다.
