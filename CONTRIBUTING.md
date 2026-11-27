# 협업 규칙

## 브랜치

| 브랜치 | 용도 | 예 |
|---|---|---|
| `main` | 배포 기준. 직접 커밋하지 않습니다 | |
| `develop` | 개발 기준. **모든 PR은 `develop`으로 보냅니다** | |
| `feat/{작업ID}-{요약}` | 기능 개발 | `feat/T2-2-place-profiles` |
| `fix/{요약}` | 버그 수정 | `fix/repair-rest-day-move` |
| `perf/{요약}` | 응답 시간·비용 개선 | `perf/compose-input-compression` |
| `prompt/{요약}` | 프롬프트 변경 | `prompt/compose-reason-rules` |
| `docs/{요약}` | 문서 | `docs/trd-idempotency` |
| `test/{요약}` | 테스트·평가셋만 추가·수정 | `test/validator-rule-10` |
| `refactor/{요약}` | 동작이 바뀌지 않는 구조 개선 | `refactor/gemini-client` |
| `chore/{요약}` | 설정·의존성·빌드·CI | `chore/setup-fastapi` |

- `{작업ID}`는 [`docs/TASKS.md`](docs/TASKS.md)의 ID(`T2-2` 등)입니다. `feat` 외의 브랜치도 해당하는 작업이 있으면 요약 앞에 붙입니다(예: `perf/T3-3-compose-input`).
- 요약은 영어 소문자와 `-`로 짧게 씁니다.
- `develop`에는 PR로만 합치고 **Squash merge**합니다. PR 제목이 최종 커밋 메시지가 됩니다.
- PR 하나에는 목적 하나만 담습니다.

### Orca 작업 공간의 브랜치
- Orca가 만든 작업 공간은 처음에 `{사용자명}/{이름}` 형식의 브랜치를 씁니다. 이 이름은 규칙에 맞지 않으므로, **작업 내용이 정해지면 첫 커밋 전에 규칙에 맞는 이름으로 바꿉니다** (`git branch -m <새 이름>`).
- 이미 원격에 올린 브랜치의 이름은 바꾸지 않습니다.
- CLI로 작업 공간을 만들 때는 처음부터 이름을 줍니다: `orca worktree create --name <이름> --branch <규칙에 맞는 브랜치> --base-branch develop`.

## 커밋 메시지

```
타입(범위): 한국어 요약

(선택) 본문: 무엇을 왜 바꿨는지

(선택) Task: T2-4
```

| 타입 | 의미 |
|---|---|
| `feat` | 기능 추가 |
| `fix` | 버그 수정 |
| `perf` | 응답 시간·비용 개선 |
| `prompt` | 프롬프트 변경 (`prompts/` 파일) |
| `docs` | 문서 |
| `refactor` | 동작이 바뀌지 않는 구조 개선 |
| `test` | 테스트·평가셋 |
| `chore` | 설정·의존성·빌드·CI |

**범위** (파이프라인 단계와 모듈 이름. 여러 곳에 걸치면 생략합니다)

| 영역 | 범위 |
|---|---|
| API | `api`, `contract` |
| 코스 구성 | `enrich`, `compose`, `repair`, `diversify`, `reason` |
| 데이터 | `batch`, `profile`, `embed`, `db` |
| 기타 | `llm`, `eval`, `config`, `infra` |

- 요약은 50자 이내로 쓰고 마침표를 붙이지 않습니다. "~한다"가 아니라 명사형으로 씁니다.
- `prompt` 타입의 범위는 프롬프트 파일 이름을 쓰고, 요약 끝에 새 버전을 적습니다.
- `Task:` 줄은 브랜치 이름에 작업 ID가 없을 때 적습니다.

예

```
feat(profile): 장소 설명문·태그 생성 배치
fix(repair): 쉬는 요일 장소를 다른 날로 옮기지 못하는 문제 수정
perf(compose): 후보 입력 압축으로 입력 토큰 40% 감소
prompt(compose): 추천 이유 금지 표현 규칙 추가 (v3)
test(eval): 코스 평가셋 생성기 추가
docs: TRD 계약 건의 갱신
```

## PR

- 기준 브랜치는 `develop`입니다.
- 제목은 커밋 메시지 규칙을 따릅니다.
- 본문에 작업 ID, 관련 기능 ID(`FUNC-xxx`), 참조한 PRD·TRD 절, 테스트 방법을 적습니다.
- **`prompt`·`perf` PR과 가중치·모델을 바꾸는 PR은 회귀 평가 결과를 바꾸기 전과 후로 나란히 적습니다.** 통과율, 기본 코스 비율, p95 응답 시간, 토큰 수가 대상입니다 ([TRD 12장](docs/TRD.md#12-테스트와-평가)).
- `docs/TASKS.md`의 상태 변경은 그 작업의 PR에 함께 넣습니다.
- 머지 전에 린트, 타입 검사, 테스트가 통과해야 합니다.
