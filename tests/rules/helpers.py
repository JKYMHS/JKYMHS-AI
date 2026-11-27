"""Spring `CourseValidatorTest`의 도움 함수를 요청(`AiCourseRequest`) 형식으로 옮긴 것.

Spring 테스트는 `CourseContext`를 직접 만든다. 여기서는 같은 값이 나오는 요청을 만든다.
"""

from datetime import date, time
from typing import Any

from app.contract import AiCourseRequest, AiCourseResponse

MONDAY = date(2026, 11, 9)
ORIGIN = {"lat": 37.5700, "lng": 126.9770}

# TimeOfDay.startTime의 역
_TIME_OF_DAY = {time(9, 0): "early", time(10, 0): "morning", time(13, 0): "afternoon"}


def place(
    content_id: int,
    open_time: str | None = None,
    close_time: str | None = None,
    last_entry: str | None = None,
    *,
    rest_days: list[str] | None = None,
    required: bool = False,
) -> dict[str, Any]:
    """Spring `place()`: 출발지에서 북쪽으로 `id × 0.001`도 떨어진 관광지. 쉬는 날 없음."""
    return {
        "contentId": content_id,
        "name": f"장소{content_id}",
        "lat": 37.5700 + content_id * 0.001,
        "lng": 126.9770,
        "category": "궁",
        "io": "OUTDOOR",
        "openTime": open_time,
        "closeTime": close_time,
        "lastEntryTime": last_entry,
        "restDays": [] if rest_days is None else rest_days,
        "eventStartDate": None,
        "eventEndDate": None,
        "required": required,
    }


def festival(content_id: int, start: date, end: date, *, required: bool = False) -> dict[str, Any]:
    """Spring `festival()`: 행사 시각을 모르고 쉬는 날도 모르는 축제."""
    return {
        "contentId": content_id,
        "name": f"축제{content_id}",
        "lat": 37.5700 + content_id * 0.001,
        "lng": 126.9770,
        "category": "축제",
        "io": "OUTDOOR",
        "openTime": None,
        "closeTime": None,
        "lastEntryTime": None,
        "restDays": None,
        "eventStartDate": start.isoformat(),
        "eventEndDate": end.isoformat(),
        "required": required,
    }


def request(
    candidates: list[dict[str, Any]],
    *,
    kids: bool = False,
    min_per_day: int,
    max_per_day: int,
    days: int = 1,
    first_day_start: time = time(10, 0),
    later_day_start: time = time(10, 0),
    origin: dict[str, float] | None = ORIGIN,
    start_date: date = MONDAY,
) -> AiCourseRequest:
    """Spring `new CourseContext(candidates, required, MONDAY, days, min, max, kids, ...)`과
    같은 값이 나오는 요청.

    꼭 포함 장소는 후보의 `required`로 정한다 (Spring `RecommendationWorker`와 같다).
    """
    end_date = date.fromordinal(start_date.toordinal() + days - 1)
    return AiCourseRequest.model_validate(
        {
            "requestId": 1,
            "conditions": {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "startTime": first_day_start.strftime("%H:%M"),
                "companion": "kids" if kids else "couple",
                "childAgeGroup": "ELEMENTARY" if kids else None,
                "pace": "relaxed",
                "indoor": False,
                "timeOfDay": _TIME_OF_DAY[later_day_start],
                "origin": origin,
            },
            "profile": {"topCategories": []},
            "candidates": candidates,
            "rules": {
                "courses": 3,
                "placesPerDay": {"min": min_per_day, "max": max_per_day},
                "lunch": "11:30-13:30",
                "dinner": "17:30-19:30",
                "noPlaceAfter": "20:00" if kids else None,
            },
            "violations": [],
        }
    )


def day(day_number: int, *ids: int, stay: int | None = 90) -> dict[str, Any]:
    """Spring `day()`: 모든 장소에 90분 머문다."""
    return {
        "dayNumber": day_number,
        "items": [{"contentId": i, "stayMinutes": stay, "reason": "이유"} for i in ids],
    }


def course(*days: dict[str, Any]) -> dict[str, Any]:
    return {"title": "코스", "summary": "", "days": list(days)}


def response(*courses: dict[str, Any]) -> AiCourseResponse:
    return AiCourseResponse.model_validate({"courses": list(courses)})


def three_of(*days: dict[str, Any]) -> AiCourseResponse:
    """Spring `threeOf()`: 같은 코스 3개."""
    one = course(*days)
    return response(one, one, one)


def each_course(*violations: str) -> list[str]:
    """같은 코스 3개가 같은 위반을 낼 때의 전체 목록 (`"코스 N: "`을 붙인다)."""
    return [f"코스 {n}: {v}" for n in range(1, 4) for v in violations]
