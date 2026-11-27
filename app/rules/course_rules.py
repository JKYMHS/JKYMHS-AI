"""Spring `CourseValidator` 규칙 1–10 (TRD 3.4).

기준은 Spring 코드다 (`JKYMHS-Backend` `develop`):

- `recommendation/service/CourseValidator.java`: 검사 순서와 위반 문장
- `recommendation/service/CourseTimeline.java`, `recommendation/entity/MealType.java`:
  시각 계산과 식사 칸
- `route/service/RouteService.java`의 `estimate`·`distanceMeters`: 직선거리 어림 이동 시간
- `recommendation/service/RecommendationWorker.java`: `CourseContext`를 만드는 방법
- `user/entity/TimeOfDay.java`: 둘째 날부터의 시작 시각

Spring은 재요청 때 `validate`가 돌려준 문장을 그대로 `violations`에 담아 보낸다.
그래서 순서와 문장이 Spring과 글자 하나까지 같아야 한다.
규칙을 바꾸려면 Spring 코드가 먼저 바뀌어야 한다.

`CourseContext`는 요청(`AiCourseRequest`)에서 만든다. Spring은 같은 값으로 요청을 만들기 때문에,
아래 두 가지를 빼면 같은 값이 나온다.

- 꼭 포함 장소의 순서: Spring은 사용자가 고른 순서(`sortOrder`), 여기서는 후보 순서(점수 순)다.
  꼭 포함 장소가 둘 이상 빠졌을 때 위반 문장의 순서만 다를 수 있다.
- 출발지가 없을 때: Spring은 출발지가 늘 있다. 여기서는 첫날 첫 장소의 이동을 0분으로 본다
  (Spring `checkHours`가 `from == null`일 때 하는 것과 같다).

출발지 좌표는 거리 계산에만 쓴다. 로그에 남기지 않는다 (TRD 8).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, time, timedelta
from enum import Enum

from app.contract import AiCourseRequest, AiCourseResponse, Candidate, Course, Point

__all__ = [
    "DayTimeline",
    "MealSlot",
    "MealType",
    "PlaceSlot",
    "course_timeline",
    "validate",
]

# CourseValidator
_MIN_STAY_MINUTES = 30
_MAX_STAY_MINUTES = 300
_DEFAULT_STAY_MINUTES = 90
_KIDS_LAST_END_MINUTES = 20 * 60

# TimeOfDay.startTime
_TIME_OF_DAY_START = {
    "early": time(9, 0),
    "morning": time(10, 0),
    "afternoon": time(13, 0),
}

# RecommendationWorker.toAiCandidate가 DayOfWeek.name()을 세 글자로 줄인다.
# 위반 문장에는 전체 이름을 쓴다.
_DAY_OF_WEEK = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")

# RouteService
_ESTIMATE_WALK_METERS_PER_MINUTE = 4000.0 / 60
_ESTIMATE_CAR_METERS_PER_MINUTE = 30000.0 / 60
_ESTIMATE_WALK_LIMIT_METERS = 1000
_EARTH_RADIUS_METERS = 6_371_000

# CourseTimeline
_EARLY_MEAL_MARGIN_MINUTES = 60
_MEAL_MINUTES = 60
_LAST_MINUTE_OF_DAY = 23 * 60 + 59


# ---------------------------------------------------------------------------
# 시각 계산 (CourseTimeline, MealType)
# ---------------------------------------------------------------------------


class MealType(Enum):
    """식사 칸. 시작 시각이 [창 시작, 창 끝 − 60분] 안일 때만 넣고, 길이는 60분이다."""

    LUNCH = (time(11, 30), time(13, 30))
    DINNER = (time(17, 30), time(19, 30))

    @property
    def window_start(self) -> int:
        return _to_minutes(self.value[0])

    @property
    def latest_start(self) -> int:
        return _to_minutes(self.value[1]) - _MEAL_MINUTES


@dataclass(frozen=True, slots=True)
class PlaceSlot:
    """장소 칸. 시각은 0시부터의 분이다 (자정을 넘기면 1440 이상)."""

    index: int
    """그날 장소 목록에서의 순서 (0부터)."""
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class MealSlot:
    """식사 칸. 시각은 0시부터의 분이다."""

    meal_type: MealType
    start: int
    end: int


type Slot = PlaceSlot | MealSlot


def _to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _to_time(minutes: int) -> time:
    """화면에 낼 시각. 0:00 아래와 23:59 위는 끝에서 멈춘다 (`CourseTimeline.toTime`)."""
    clamped = min(max(minutes, 0), _LAST_MINUTE_OF_DAY)
    return time(clamped // 60, clamped % 60)


def _hhmm(value: time) -> str:
    """Java `LocalTime.toString()` (초가 0이면 `HH:mm`)."""
    return value.strftime("%H:%M")


def _in_window(cursor: int, meal_type: MealType) -> bool:
    return meal_type.window_start <= cursor <= meal_type.latest_start


def _meals(cursor: int, next_minutes: int, slots: list[Slot], done: set[MealType]) -> int:
    for meal_type in MealType:
        if meal_type in done:
            continue
        window_start = meal_type.window_start
        if _in_window(cursor, meal_type):
            slots.append(MealSlot(meal_type, cursor, cursor + _MEAL_MINUTES))
            cursor += _MEAL_MINUTES
            done.add(meal_type)
        elif (
            window_start - _EARLY_MEAL_MARGIN_MINUTES <= cursor < window_start
            and cursor + next_minutes > meal_type.latest_start
        ):
            slots.append(MealSlot(meal_type, window_start, window_start + _MEAL_MINUTES))
            cursor = window_start + _MEAL_MINUTES
            done.add(meal_type)
    return cursor


def _layout(
    day_start: time, stay_minutes: Sequence[int], move_minutes: Sequence[int]
) -> list[Slot]:
    """하루 일정의 칸 (`CourseTimeline.layout`).

    `move_minutes[i]`는 i번째 장소로 "들어오는" 이동 시간이다 (출발점 → 첫 장소 포함).
    """
    slots: list[Slot] = []
    done: set[MealType] = set()
    cursor = _to_minutes(day_start)
    for i, (stay, move) in enumerate(zip(stay_minutes, move_minutes, strict=True)):
        if i > 0:
            cursor = _meals(cursor, move + stay, slots, done)
        cursor += move
        slots.append(PlaceSlot(i, cursor, cursor + stay))
        cursor += stay
    if stay_minutes:
        for meal_type in MealType:
            if meal_type not in done and _in_window(cursor, meal_type):
                slots.append(MealSlot(meal_type, cursor, cursor + _MEAL_MINUTES))
                cursor += _MEAL_MINUTES
                done.add(meal_type)
    return slots


# ---------------------------------------------------------------------------
# 이동 시간 어림 (RouteService.estimate)
# ---------------------------------------------------------------------------


def _java_round(value: float) -> int:
    """Java `Math.round(double)`: 가장 가까운 정수, 0.5는 +∞ 쪽으로."""
    floor = math.floor(value)
    return floor + 1 if value - floor >= 0.5 else floor


def _distance_meters(from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> int:
    """하버사인 직선거리(m) (`RouteService.distanceMeters`)."""
    d_lat = math.radians(to_lat - from_lat)
    d_lng = math.radians(to_lng - from_lng)
    a = math.sin(d_lat / 2) * math.sin(d_lat / 2) + math.cos(math.radians(from_lat)) * math.cos(
        math.radians(to_lat)
    ) * math.sin(d_lng / 2) * math.sin(d_lng / 2)
    return _java_round(2 * _EARTH_RADIUS_METERS * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _estimate_minutes(from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> int:
    """직선거리 어림 이동 시간(분) (`RouteService.estimate`).

    1km 이하는 도보 4km/h, 그 이상은 자동차 30km/h로 본다.
    """
    distance = _distance_meters(from_lat, from_lng, to_lat, to_lng)
    if distance <= _ESTIMATE_WALK_LIMIT_METERS:
        speed = _ESTIMATE_WALK_METERS_PER_MINUTE
    else:
        speed = _ESTIMATE_CAR_METERS_PER_MINUTE
    return max(1, math.ceil(distance / speed))


# ---------------------------------------------------------------------------
# 요청 → CourseContext (RecommendationWorker)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Context:
    candidates: dict[int, Candidate]
    required_ids: list[int]
    start_date: date
    days: int
    min_per_day: int
    max_per_day: int
    kids: bool
    first_day_start: time
    later_day_start: time
    origin: Point | None
    courses: int

    def day_start(self, day_number: int) -> time:
        return self.first_day_start if day_number == 1 else self.later_day_start


def _context(request: AiCourseRequest) -> _Context:
    candidates: dict[int, Candidate] = {}
    for candidate in request.candidates:
        # Collectors.toMap(..., (a, b) -> a, LinkedHashMap::new): 같은 id는 먼저 온 것
        candidates.setdefault(candidate.content_id, candidate)
    conditions = request.conditions
    return _Context(
        candidates=candidates,
        required_ids=[c.content_id for c in candidates.values() if c.required],
        start_date=conditions.start_date,
        days=conditions.days(),
        min_per_day=request.rules.places_per_day.min,
        max_per_day=request.rules.places_per_day.max,
        kids=conditions.companion == "kids",
        first_day_start=conditions.start_time,
        later_day_start=_TIME_OF_DAY_START[conditions.time_of_day],
        origin=conditions.origin,
        courses=request.rules.courses,
    )


def _stay_of(stay_minutes: int | None) -> int:
    """비었거나 30–300분 밖이면 90분 (`CourseValidator.stayOf`)."""
    if stay_minutes is None or not _MIN_STAY_MINUTES <= stay_minutes <= _MAX_STAY_MINUTES:
        return _DEFAULT_STAY_MINUTES
    return stay_minutes


def _moves(places: Sequence[Candidate], day_origin: tuple[float, float] | None) -> list[int]:
    moves: list[int] = []
    from_point = day_origin
    for place in places:
        if from_point is None:
            moves.append(0)
        else:
            moves.append(_estimate_minutes(*from_point, place.lat, place.lng))
        from_point = (place.lat, place.lng)
    return moves


def _origin_point(context: _Context) -> tuple[float, float] | None:
    return None if context.origin is None else (context.origin.lat, context.origin.lng)


# ---------------------------------------------------------------------------
# 공개 함수
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DayTimeline:
    """하루 일정의 임시 시각. Spring이 규칙 10·9를 검사할 때 매기는 시각과 같다.

    `content_ids`·`stay_minutes`·`move_minutes`는 `PlaceSlot.index`로 찾는다.
    """

    day_number: int
    date: date
    day_start: time
    content_ids: list[int]
    """그날 장소 (후보에 없는 것과 코스 안에서 이미 나온 것은 빠짐)."""
    stay_minutes: list[int]
    """머무는 시간. Spring처럼 비었거나 30–300분 밖이면 90분."""
    move_minutes: list[int]
    """각 장소로 들어오는 이동 시간 (첫날은 출발지, 다음 날은 전날 마지막 장소부터)."""
    slots: list[Slot]
    """장소·식사 칸. 시각 순서."""


def course_timeline(request: AiCourseRequest, course: Course) -> list[DayTimeline]:
    """코스 하나의 날마다 임시 시각을 매긴다 (자체 점검·보정용).

    `dayNumber` 1–N을 차례로 본다. 같은 `dayNumber`가 여럿이면 처음 것, 없으면 장소 없는 날이다.
    날짜 모양이 맞는 코스라면 `validate`가 검사에 쓰는 시각과 같다.
    """
    context = _context(request)
    seen: set[int] = set()
    previous_last = _origin_point(context)
    timelines: list[DayTimeline] = []
    for day_number in range(1, context.days + 1):
        day = next((d for d in course.days if d.day_number == day_number), None)
        places: list[Candidate] = []
        stays: list[int] = []
        for item in [] if day is None else day.items:
            candidate = context.candidates.get(item.content_id)
            if candidate is None or candidate.content_id in seen:
                continue
            seen.add(candidate.content_id)
            places.append(candidate)
            stays.append(_stay_of(item.stay_minutes))
        moves = _moves(places, previous_last)
        day_start = context.day_start(day_number)
        timelines.append(
            DayTimeline(
                day_number=day_number,
                date=context.start_date + timedelta(days=day_number - 1),
                day_start=day_start,
                content_ids=[p.content_id for p in places],
                stay_minutes=stays,
                move_minutes=moves,
                slots=_layout(day_start, stays, moves),
            )
        )
        if places:
            previous_last = (places[-1].lat, places[-1].lng)
    return timelines


def validate(request: AiCourseRequest, response: AiCourseResponse) -> list[str]:
    """응답이 어긴 규칙을 Spring `CourseValidator.validate`와 같은 순서·문장으로 돌려준다.

    빈 목록이면 Spring 검증을 통과한다.
    """
    context = _context(request)
    if len(response.courses) < context.courses:
        return [f"코스는 {context.courses}개가 필요합니다."]
    violations: list[str] = []
    for index in range(context.courses):
        _validate_course(index + 1, response.courses[index], context, violations)
    return violations


def _validate_course(
    course_number: int, course: Course, context: _Context, violations: list[str]
) -> None:
    prefix = f"코스 {course_number}: "
    day_numbers: set[int] = set()
    for day in course.days:
        if not 1 <= day.day_number <= context.days or day.day_number in day_numbers:
            violations.append(f"{prefix}dayNumber는 1~{context.days}이 한 번씩 있어야 합니다.")
            return
        day_numbers.add(day.day_number)
    if len(day_numbers) != context.days:
        violations.append(f"{prefix}날짜 {context.days}일이 모두 있어야 합니다.")
        return

    seen: set[int] = set()
    previous_last = _origin_point(context)
    for day in sorted(course.days, key=lambda d: d.day_number):
        day_date = context.start_date + timedelta(days=day.day_number - 1)
        items = day.items
        if not context.min_per_day <= len(items) <= context.max_per_day:
            violations.append(
                f"{prefix}{day.day_number}일차 장소는 "
                f"{context.min_per_day}~{context.max_per_day}곳이어야 합니다 ({len(items)}곳)."
            )
        places: list[Candidate] = []
        stays: list[int] = []
        for item in items:
            candidate = context.candidates.get(item.content_id)
            if candidate is None:
                violations.append(f"{prefix}후보에 없는 장소입니다: {item.content_id}")
                continue
            if candidate.content_id in seen:
                violations.append(f"{prefix}같은 장소가 두 번 들어갔습니다: {candidate.content_id}")
                continue
            seen.add(candidate.content_id)
            places.append(candidate)
            stays.append(_stay_of(item.stay_minutes))
            if not candidate.required:
                _check_date(prefix, candidate, day_date, violations)
        _check_hours(prefix, day.day_number, places, stays, previous_last, context, violations)
        if places:
            previous_last = (places[-1].lat, places[-1].lng)
    for required_id in context.required_ids:
        if required_id not in seen:
            violations.append(f"{prefix}꼭 포함할 장소가 빠졌습니다: {required_id}")


def _check_date(prefix: str, candidate: Candidate, day: date, violations: list[str]) -> None:
    content_id = candidate.content_id
    if not candidate.runs_on(day):
        violations.append(f"{prefix}축제 {content_id}는 {day.isoformat()}에 열리지 않습니다.")
    day_of_week = _DAY_OF_WEEK[day.weekday()]
    if candidate.rest_days is not None and day_of_week[:3] in candidate.rest_days:
        violations.append(f"{prefix}{content_id}는 {day.isoformat()}({day_of_week})에 쉽니다.")


def _check_hours(
    prefix: str,
    day_number: int,
    places: list[Candidate],
    stays: list[int],
    day_origin: tuple[float, float] | None,
    context: _Context,
    violations: list[str],
) -> None:
    moves = _moves(places, day_origin)
    for slot in _layout(context.day_start(day_number), stays, moves):
        if not isinstance(slot, PlaceSlot):
            continue
        candidate = places[slot.index]
        if context.kids and slot.end > _KIDS_LAST_END_MINUTES:
            violations.append(
                f"{prefix}아이와 가는 일정은 20:00 전에 끝나야 합니다: {candidate.content_id}"
            )
        if not candidate.required:
            _check_open(prefix, candidate, slot, violations)


def _check_open(prefix: str, candidate: Candidate, slot: PlaceSlot, violations: list[str]) -> None:
    # 요청의 openTime·closeTime은 축제면 이미 행사 시작·종료 시각이다
    # (RecommendationWorker.toAiCandidate)
    open_time = candidate.open_time
    close_time = candidate.close_time
    # 모르는 영업시간과 자정을 넘기는 영업(22:00~02:00)은 보지 않는다
    if open_time is None or close_time is None or not close_time > open_time:
        return
    open_minutes = _to_minutes(open_time)
    close_minutes = _to_minutes(close_time)
    last_entry = candidate.last_entry_time
    last_entry_minutes = close_minutes if last_entry is None else _to_minutes(last_entry)
    if slot.start < open_minutes or slot.start > last_entry_minutes or slot.end > close_minutes:
        violations.append(
            f"{prefix}{candidate.content_id} 방문 시각 "
            f"{_hhmm(_to_time(slot.start))}~{_hhmm(_to_time(slot.end))}이 "
            f"영업시간 {_hhmm(open_time)}~{_hhmm(close_time)} 밖입니다."
        )
