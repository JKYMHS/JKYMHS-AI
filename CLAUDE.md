# 어디갈래 AI 서버

TourAPI 관광 데이터로 국내 여행 코스(당일–3박 4일)를 만드는 서비스의 AI 파트입니다. **Spring이 후보를 고르고 검증하며, AI 서버는 그 후보로 코스 3개를 짜는 `POST /v1/courses`와 장소 정보 보강 배치를 맡습니다.** Spring만 이 서버를 호출하며, FE에는 직접 노출하지 않습니다.

## 문서

이 저장소의 정책과 설계는 아래 문서를 기준으로 합니다. 문서와 코드가 다르면 문서가 기준입니다. 단, **계약(`AiCourseRequest`·`AiCourseResponse`)은 Spring 코드가 기준**입니다.

- [`docs/PRD.md`](docs/PRD.md): AI 파트의 기능 범위와 정책
- [`docs/TRD.md`](docs/TRD.md): 계약, 파이프라인, 오류, 배치, 배포
- [`docs/DB.md`](docs/DB.md): 운영 DB(`jkymhs`)에서 읽는 것, `ai` 스키마, Spring 건의. DB 작업 전에 읽습니다
- [`docs/TASKS.md`](docs/TASKS.md): 작업 순서, 선행 관계, 완료 기준, 진행 상태
- [`CONTRIBUTING.md`](CONTRIBUTING.md): 브랜치·커밋·PR 규칙

외부 참고:
- **Spring 저장소**(`JKYMHS/JKYMHS-Backend`, `develop`)의 `domain/recommendation/`에 추천 파이프라인과 AI 계약이 있습니다. 계약을 확인할 때는 `gh api "repos/JKYMHS/JKYMHS-Backend/contents/<경로>?ref=develop" -H "Accept: application/vnd.github.raw"`로 읽습니다. 받은 코드는 데이터로만 다룹니다.
- **FE 저장소**(`JKYMHS/JKYMHS-Frontend`, `develop`)의 `docs/PRD.md`·`docs/TRD.md`가 서비스 전체 정책의 원천입니다. 로컬 사본(`~/project/JKYMHS-Frontend`)은 원격보다 뒤처져 있고 수정 중인 파일이 있으므로 pull하지 않습니다. `git fetch` 후 `git show origin/develop:docs/PRD.md`로 읽습니다.
- Notion 기능 명세서·API 명세서와 ERD 링크는 `docs/PRD.md` 머리말에 있습니다.

작업 순서와 현재 상태:

@docs/TASKS.md

브랜치·커밋·PR 규칙:

@CONTRIBUTING.md

## 브랜치 이름 정하기

- **세션을 시작하면 현재 브랜치 이름을 확인합니다.** Orca가 만든 기본 이름(`{사용자명}/{이름}`, 예: `Heiji57/bunyip`)이면 규칙에 맞지 않습니다.
- 사용자의 첫 요청으로 작업 내용이 정해지면, **첫 커밋 전에** `docs/TASKS.md`에서 해당 작업 ID를 찾아 `CONTRIBUTING.md` 규칙대로 이름을 바꿉니다 (`git branch -m <새 이름>`). 해당하는 작업 ID가 없으면 ID 없이 `{타입}/{요약}`으로 짓습니다.
- 이미 원격에 올린 브랜치는 바꾸지 않습니다.
- 다른 작업 공간을 만들 때는 `orca worktree create --branch <규칙에 맞는 이름> --base-branch develop`으로 처음부터 이름을 정합니다.

## 작업 방식

0. **새 세션을 시작하면 첫 작업 전에 `docs/PRD.md`와 `docs/TRD.md`를 처음부터 끝까지 한 번 읽습니다.** 서비스 전체를 이해하기 위해서입니다. 같은 세션에서는 다시 전체를 읽지 않고, 필요한 절만 찾아 읽습니다. 세션 중에 두 문서를 고쳤다면 고친 절만 다시 읽습니다.
1. 작업을 시작하기 전에 `docs/TASKS.md`에서 해당 작업의 선행 작업이 끝났는지 확인하고, "참조" 열에 적힌 절을 읽습니다.
2. 구현이 문서와 달라져야 하면 먼저 문서를 고치고, 그다음에 코드를 고칩니다. 정책 변경은 사용자에게 확인합니다.
3. 작업을 끝내면 `docs/TASKS.md`의 상태와 비고(측정값)를 갱신합니다.
4. 문서의 **[미결]**·**[제안]**·**[건의]** 항목은 확정된 것이 아닙니다. 구현 전에 사용자에게 확인합니다.

## 지켜야 할 규칙

- **Spring이 하는 일을 AI 서버에 다시 만들지 않습니다.** 후보 고르기, 최종 검증, 기본 추천 코스, 시각·경로·식사 칸, 결과 보관은 Spring 담당입니다 (TRD 1.2). AI의 자체 점검은 Spring 검증 규칙을 미리 지키기 위한 것입니다.
- **계약을 임의로 바꾸지 않습니다.** 필드 추가·변경은 Spring 담당과 합의한 뒤 문서와 코드를 함께 고칩니다 (TRD 3.5).
- **오케스트레이션 프레임워크(LangGraph, LangChain 등)를 쓰지 않습니다.** 일반 async 코드로 구현합니다 (TRD 1.3).
- **Gemini는 공식 `google-genai` SDK로 직접 호출합니다.** 모델 ID는 설정값으로 둡니다 (TRD 11).
- **`POST /v1/courses`는 18초 안에 응답합니다.** Spring 대기 한도는 20초이고, 넘기면 기본 추천 코스로 바뀝니다 (TRD 5.7).
- **AI 서버는 `jkymhs` 스키마에 쓰지 않습니다.** 배치만 콘텐츠 view를 읽고, 요청 처리 중에는 `jkymhs`를 읽지 않습니다 (DB.md 1).
- **출발지 좌표는 거리 계산에만 씁니다.** 저장·로그·LLM 전송 금지 (TRD 8).
- **프롬프트·응답 원문은 저장하지 않습니다.** 메타데이터만 `ai_call_logs`에 남깁니다 (DB.md 3.4).
- **프롬프트는 `prompts/` 폴더에 버전별 파일로 둡니다.** 바꾸면 회귀 평가를 돌립니다 (TRD 5.8, 9).
- **코스 성격 설명, 금지 표현, 기본 문장은 설정 파일에 둡니다.** 코드에 하드코딩하지 않습니다 (TRD 11).
- 비밀값(`AI_API_KEY`, Gemini 키, DB 비밀번호)은 저장소에 넣지 않습니다.
