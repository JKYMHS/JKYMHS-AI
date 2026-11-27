"""`POST /v1/courses` 계약 모델 (TRD 3.2–3.3).

계약의 기준은 Spring 코드다 (`JKYMHS-Backend` `develop`,
`domain/recommendation/client/ai/AiCourseRequest.java`·`AiCourseResponse.java`).
필드를 바꾸려면 Spring 담당과 먼저 합의한다 (TRD 3.5).

- JSON 필드 이름은 Spring과 같은 camelCase, 파이썬 속성은 snake_case다.
- 시각은 `"HH:mm"`, 날짜는 `"YYYY-MM-DD"`로 읽고 쓴다.
- Java의 원시 타입(`int`·`double`·`boolean`)은 필수 값, `null`이 올 수 있는 값은 `| None`이다.
  `| None` 필드는 Jackson record처럼 키가 빠져도 `None`으로 읽는다.
- 요청은 모르는 필드를 무시한다. Spring이 필드를 더해도 깨지지 않게 하기 위해서다.
"""

import re
from datetime import date, time
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer
from pydantic.alias_generators import to_camel

_HHMM = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")


def _parse_hhmm(value: Any) -> Any:
    """`"HH:mm"`만 받는다 (Spring `@JsonFormat(pattern = "HH:mm")`). `time` 객체는 그대로 둔다."""
    if isinstance(value, str):
        match = _HHMM.fullmatch(value)
        if match is None:
            raise ValueError(f"시각은 HH:mm 형식이어야 합니다: {value!r}")
        return time(int(match[1]), int(match[2]))
    return value


def _format_hhmm(value: time) -> str:
    return value.strftime("%H:%M")


HhMm = Annotated[
    time,
    BeforeValidator(_parse_hhmm),
    PlainSerializer(_format_hhmm, return_type=str, when_used="json"),
]
"""`"HH:mm"` 문자열 ↔ `datetime.time`."""


def _none_to_empty(value: Any) -> Any:
    return [] if value is None else value


# Spring enum의 code 값 (JKYMHS-Backend `develop`)
Companion = Literal["alone", "couple", "friends", "kids", "parents"]  # global/model/Companion
ChildAgeGroup = Literal["INFANT", "ELEMENTARY", "TEEN"]  # global/model/ChildAgeGroup
Pace = Literal["relaxed", "packed"]  # user/entity/Pace
TimeOfDay = Literal["early", "morning", "afternoon"]  # user/entity/TimeOfDay
Io = Literal["INDOOR", "OUTDOOR", "MIXED"]  # content/entity/IoType
# RecommendationWorker.toAiCandidate: DayOfWeek.name().substring(0, 3)
RestDay = Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


class _ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="ignore",
    )


class _RequestModel(_ContractModel):
    """요청은 읽기만 한다 (Java record처럼 바꾸지 않는다)."""

    model_config = ConfigDict(frozen=True)


# ---------------------------------------------------------------------------
# 요청: AiCourseRequest
# ---------------------------------------------------------------------------


class Point(_RequestModel):
    lat: float
    lng: float


class Conditions(_RequestModel):
    start_date: date
    end_date: date
    start_time: HhMm
    companion: Companion
    child_age_group: ChildAgeGroup | None = None
    pace: Pace
    indoor: bool
    time_of_day: TimeOfDay
    """둘째 날부터의 시작 시간대."""
    origin: Point | None = None
    """첫째 날 출발지. 거리 계산에만 쓴다. 저장·로그·LLM 전송 금지 (TRD 8)."""

    def days(self) -> int:
        """여행 일수 (`endDate - startDate + 1`)."""
        return (self.end_date - self.start_date).days + 1


class TopCategory(_RequestModel):
    lcls2: str
    score: float


class Profile(_RequestModel):
    top_categories: list[TopCategory]


class Candidate(_RequestModel):
    content_id: int
    name: str
    lat: float
    lng: float
    category: str | None = None
    """소분류 이름 ("박물관")."""
    io: Io | None = None
    open_time: HhMm | None = None
    """축제면 행사 시작 시각."""
    close_time: HhMm | None = None
    """축제면 행사 종료 시각."""
    last_entry_time: HhMm | None = None
    rest_days: list[RestDay] | None = None
    """빈 목록 = 쉬는 날 없음, `None` = 모름."""
    event_start_date: date | None = None
    """축제일 때만."""
    event_end_date: date | None = None
    required: bool
    """꼭 포함할 장소."""

    def runs_on(self, day: date) -> bool:
        """축제면 그날 열리는지. 축제가 아니면 항상 `True`."""
        if self.event_start_date is None or self.event_end_date is None:
            return True
        return self.event_start_date <= day <= self.event_end_date


class PlacesPerDay(_RequestModel):
    min: int
    max: int


class Rules(_RequestModel):
    courses: int
    places_per_day: PlacesPerDay
    lunch: str
    """식사 시간대 `"HH:mm-HH:mm"` (예: `"11:30-13:30"`)."""
    dinner: str
    no_place_after: str | None = None
    """아이와 가면 `"20:00"` (이 시각을 넘겨 끝나는 장소 금지), 아니면 `None`."""


class AiCourseRequest(_RequestModel):
    request_id: int
    conditions: Conditions
    profile: Profile
    candidates: list[Candidate]
    """Spring 점수 높은 순. 꼭 포함할 장소는 `required=True`."""
    rules: Rules
    violations: Annotated[list[str], BeforeValidator(_none_to_empty)] = Field(default_factory=list)
    """직전 응답이 어긴 규칙 (다시 요청할 때만). 없거나 `null`이면 빈 목록."""

    def with_violations(self, violations: list[str]) -> "AiCourseRequest":
        return self.model_copy(update={"violations": list(violations)})


# ---------------------------------------------------------------------------
# 응답: AiCourseResponse
# ---------------------------------------------------------------------------


class Item(_ContractModel):
    content_id: int
    stay_minutes: int | None = None
    """머무는 시간(분). 비었거나 이상한 값이면 Spring이 90분으로 바꾼다."""
    reason: str
    """화면에 보여줄 추천 이유."""


class Day(_ContractModel):
    day_number: int
    items: list[Item]


class Course(_ContractModel):
    title: str
    summary: str
    days: list[Day]


class AiCourseResponse(_ContractModel):
    courses: list[Course]
