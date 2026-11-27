"""LLM 없이 "가까운 곳 먼저"로 코스를 짜는 임시 구현 (T1-4).

Spring의 `NearestCoursePlanner`(mock AI·기본 추천 코스)와 같은 방식이다.
Spring 연동을 먼저 검증하려는 것이며, LLM 구현(T3-7)으로 바뀐다.

- 코스 n번째(0부터)는 꼭 포함 장소 + 나머지 후보를 앞에서 `n × 하루 최대 장소 수`만큼 밀어서
  고른 곳들로 짠다. 후보가 모자라면 앞에서부터 이어 고른다(Spring은 처음부터 다시 고른다).
- 하루 장소 수는 `placesPerDay.max`. 날마다 출발점(첫날은 출발지, 다음 날은 전날 마지막 장소)에서
  가장 가까운 곳을 차례로 고른다. 고른 장소가 그날 모자라면 남은 후보에서 채운다.
  후보가 모자라 모든 날을 최대로 채울 수 없으면, 뒷날의 최소 수(`placesPerDay.min`)를 남겨 둔다.
- 축제 기간 밖과 쉬는 요일에는 넣지 않는다. 꼭 포함 장소는 이 검사에서 빠지지만(TRD 3.4),
  되도록 여는 날에 넣고, 남은 칸이 모자랄 때만 날과 관계없이 넣는다.
- 방문 시각(규칙 9·10)은 Spring이 계산하므로 여기서 검사하지 않는다.

출발지 좌표는 거리 계산에만 쓰고 로그에 남기지 않는다 (TRD 8).
"""

import json
import math
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.contract import AiCourseRequest, AiCourseResponse, Candidate, Course, Day, Item

TEXTS_PATH = Path(__file__).resolve().parents[2] / "config" / "compose_stub.json"

# date.weekday() 순서 (월=0)
_WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


class _TextsModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, frozen=True, extra="ignore")


class CourseText(_TextsModel):
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class StubTexts(_TextsModel):
    """`config/compose_stub.json`: 코스 제목·요약과 추천 이유의 기본 문장."""

    courses: list[CourseText]
    extra_course: CourseText
    """`courses`보다 많이 요청받으면 쓴다. `{n}`은 코스 번호(1부터)."""
    reason: str
    """`{category}`는 후보의 소분류 이름."""
    reason_no_category: str
    stay_minutes: int = Field(gt=0)


@lru_cache
def load_texts(path: Path = TEXTS_PATH) -> StubTexts:
    return StubTexts.model_validate(json.loads(path.read_text(encoding="utf-8")))


def is_open_on(candidate: Candidate, day: date) -> bool:
    """축제면 기간 안이고, 쉬는 요일이 아닌지. 쉬는 요일을 모르면(`None`) 연다고 본다."""
    if not candidate.runs_on(day):
        return False
    return not candidate.rest_days or _WEEKDAYS[day.weekday()] not in candidate.rest_days


def plan(
    request: AiCourseRequest, texts: StubTexts, reason_max_chars: int = 40
) -> AiCourseResponse:
    conditions = request.conditions
    dates = [conditions.start_date + timedelta(days=i) for i in range(conditions.days())]
    per_day = max(request.rules.places_per_day.max, 0)
    per_day_min = min(max(request.rules.places_per_day.min, 0), per_day)

    candidates = _dedupe(request.candidates)
    required = [c for c in candidates if c.required]
    # 여행 기간 중 하루도 열지 않는 장소는 처음부터 뺀다.
    others = [c for c in candidates if not c.required and any(is_open_on(c, d) for d in dates)]
    wanted = max(0, len(dates) * per_day - len(required))
    origin = None if conditions.origin is None else (conditions.origin.lat, conditions.origin.lng)

    def reason_of(candidate: Candidate) -> str:
        if candidate.category:
            text = texts.reason.format(category=candidate.category)
        else:
            text = texts.reason_no_category
        return text[:reason_max_chars]

    courses: list[Course] = []
    for n in range(request.rules.courses):
        ordered = _rotate(others, n * per_day)
        chosen = required + ordered[:wanted]
        spare = ordered[wanted:]
        text = _course_text(texts, n)
        days = _split(
            chosen, spare, dates, (per_day_min, per_day), origin, texts.stay_minutes, reason_of
        )
        courses.append(Course(title=text.title, summary=text.summary[:reason_max_chars], days=days))
    return AiCourseResponse(courses=courses)


def _course_text(texts: StubTexts, n: int) -> CourseText:
    if n < len(texts.courses):
        return texts.courses[n]
    extra = texts.extra_course
    return CourseText(title=extra.title.format(n=n + 1), summary=extra.summary)


def _dedupe(candidates: Sequence[Candidate]) -> list[Candidate]:
    """같은 `contentId`가 여러 번 오면 앞의 것만 남긴다. 하나라도 꼭 포함이면 꼭 포함."""
    by_id: dict[int, Candidate] = {}
    for c in candidates:
        first = by_id.get(c.content_id)
        if first is None:
            by_id[c.content_id] = c
        elif c.required and not first.required:
            by_id[c.content_id] = first.model_copy(update={"required": True})
    return list(by_id.values())


def _rotate(items: list[Candidate], offset: int) -> list[Candidate]:
    if not items:
        return []
    k = offset % len(items)
    return items[k:] + items[:k]


def _split(
    chosen: list[Candidate],
    spare: list[Candidate],
    dates: list[date],
    places_per_day: tuple[int, int],
    origin: tuple[float, float] | None,
    stay_minutes: int,
    reason_of: Callable[[Candidate], str],
) -> list[Day]:
    per_day_min, per_day = places_per_day
    remaining = list(chosen)
    spare = list(spare)
    position = origin
    days: list[Day] = []
    for index, day in enumerate(dates):
        slots_left = (len(dates) - index) * per_day
        opens_today = _opens_on(day)
        # 장소가 모자라면 남은 날마다 최소 수만큼 남겨 둔다(앞날만 꽉 차고 뒷날이 비지 않게).
        reserve = per_day_min * (len(dates) - index - 1)
        items: list[Item] = []
        while len(items) < per_day:
            if len(items) >= per_day_min and len(remaining) + len(spare) <= reserve:
                break
            required_left = sum(1 for c in remaining if c.required)
            only_required = required_left > 0 and required_left >= slots_left - len(items)
            if only_required:
                pick = _nearest(remaining, position, _is_required)
            else:
                pick = _nearest(remaining, position, opens_today)
            source = remaining
            if pick is None and not only_required:
                pick = _nearest(spare, position, opens_today)
                source = spare
            if pick is None:
                break
            source.remove(pick)
            items.append(
                Item(content_id=pick.content_id, stay_minutes=stay_minutes, reason=reason_of(pick))
            )
            position = (pick.lat, pick.lng)
        days.append(Day(day_number=index + 1, items=items))
    return days


def _opens_on(day: date) -> Callable[[Candidate], bool]:
    return lambda candidate: is_open_on(candidate, day)


def _is_required(candidate: Candidate) -> bool:
    return candidate.required


def _nearest(
    candidates: list[Candidate],
    position: tuple[float, float] | None,
    allowed: Callable[[Candidate], bool],
) -> Candidate | None:
    """`position`에서 가장 가까운 후보. 출발점이 없으면 앞(점수 높은 순)의 후보."""
    best: Candidate | None = None
    best_distance = math.inf
    for c in candidates:
        if not allowed(c):
            continue
        if position is None:
            return c
        lat, lng = position
        d_lat = c.lat - lat
        d_lng = (c.lng - lng) * math.cos(math.radians(lat))
        distance = d_lat * d_lat + d_lng * d_lng
        if distance < best_distance:
            best_distance = distance
            best = c
    return best
