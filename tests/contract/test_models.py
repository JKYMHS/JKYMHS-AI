"""계약 모델 테스트 (TRD 3.2–3.3, 9).

예시 JSON은 Spring(`AiCourseRequest`·`AiCourseResponse`, Jackson 기본 설정)이 보내고 받는 형식이다.
Jackson은 null 필드도 그대로 쓰므로 왕복 결과에 null이 남아야 한다.
"""

import json
from datetime import date, time
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.contract import AiCourseRequest, AiCourseResponse, Candidate, Conditions, Item

FIXTURES = Path(__file__).parent / "fixtures"
REQUEST_FIXTURES = ["request_day_trip.json", "request_kids_3days_required_festival.json"]


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


def _request(**overrides: Any) -> dict[str, Any]:
    data = _load("request_day_trip.json")
    data.update(overrides)
    return data


def _candidate(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = _load("request_day_trip.json")["candidates"][0]
    data.update(overrides)
    return data


# --- 왕복 ---------------------------------------------------------------------


@pytest.mark.parametrize("name", REQUEST_FIXTURES)
def test_request_round_trip(name: str) -> None:
    raw = (FIXTURES / name).read_text(encoding="utf-8")

    model = AiCourseRequest.model_validate_json(raw)

    assert json.loads(model.model_dump_json()) == json.loads(raw)


@pytest.mark.parametrize("name", REQUEST_FIXTURES)
def test_request_round_trip_from_python_dict(name: str) -> None:
    """FastAPI처럼 이미 파싱한 dict에서 읽어도 같다."""
    data = _load(name)

    model = AiCourseRequest.model_validate(data)

    assert model.model_dump(mode="json") == data


def test_response_round_trip() -> None:
    raw = (FIXTURES / "response.json").read_text(encoding="utf-8")

    model = AiCourseResponse.model_validate_json(raw)

    assert json.loads(model.model_dump_json()) == json.loads(raw)


def test_spring_test_response_is_readable() -> None:
    """Spring `HttpAiCourseClientTest.contract`가 쓰는 응답."""
    model = AiCourseResponse.model_validate_json(
        '{"courses": [{"title": "가족 코스", "summary": "궁과 박물관", "days": [{"dayNumber": 1,'
        ' "items": [{"contentId": 1001, "stayMinutes": 80, "reason": "아이와 걷기 좋음"}]}]}]}'
    )

    item = model.courses[0].days[0].items[0]
    assert model.courses[0].title == "가족 코스"
    assert (item.content_id, item.stay_minutes) == (1001, 80)


# --- 이름 ---------------------------------------------------------------------


def test_python_attributes_are_snake_case_and_json_is_camel_case() -> None:
    model = AiCourseRequest.model_validate(_load("request_kids_3days_required_festival.json"))

    assert model.request_id == 7
    assert model.conditions.child_age_group == "ELEMENTARY"
    assert model.rules.places_per_day.max == 2
    assert model.rules.no_place_after == "20:00"
    assert model.candidates[0].last_entry_time == time(17, 0)
    dumped = model.model_dump(mode="json")
    assert "requestId" in dumped
    assert "placesPerDay" in dumped["rules"]


def test_response_can_be_built_with_snake_case_names() -> None:
    item = Item(content_id=1, stay_minutes=60, reason="이유")

    assert item.model_dump(mode="json") == {"contentId": 1, "stayMinutes": 60, "reason": "이유"}


# --- 시각·날짜 형식 -----------------------------------------------------------


def test_times_and_dates_are_parsed() -> None:
    model = AiCourseRequest.model_validate(_load("request_kids_3days_required_festival.json"))

    assert model.conditions.start_date == date(2026, 12, 20)
    assert model.conditions.start_time == time(13, 0)
    festival = model.candidates[1]
    assert (festival.open_time, festival.close_time) == (time(17, 0), time(23, 0))
    assert festival.event_start_date == date(2026, 12, 12)


def test_times_and_dates_are_serialized_as_hhmm_and_iso_date() -> None:
    data = _request()
    data["conditions"]["startTime"] = "09:05"

    dumped = AiCourseRequest.model_validate(data).model_dump(mode="json")

    assert dumped["conditions"]["startTime"] == "09:05"
    assert dumped["conditions"]["startDate"] == "2026-12-20"


def test_time_objects_are_accepted_from_python() -> None:
    candidate = Candidate.model_validate(_candidate(openTime=time(8, 30)))

    assert candidate.model_dump(mode="json")["openTime"] == "08:30"


@pytest.mark.parametrize(
    "bad", ["25:00", "24:00", "12:60", "9:00", "09:00:00", "0900", "", "aa:bb"]
)
def test_invalid_time_is_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        Candidate.model_validate(_candidate(openTime=bad))


def test_invalid_date_is_rejected() -> None:
    data = _request()
    data["conditions"]["startDate"] = "2026-13-01"

    with pytest.raises(ValidationError):
        AiCourseRequest.model_validate(data)


# --- null과 빈 배열 -----------------------------------------------------------


def test_rest_days_null_means_unknown_and_empty_means_no_rest_day() -> None:
    model = AiCourseRequest.model_validate(_load("request_day_trip.json"))
    museum, park, street = model.candidates

    assert museum.rest_days == ["MON"]
    assert park.rest_days == []
    assert street.rest_days is None
    dumped = model.model_dump(mode="json")["candidates"]
    assert (dumped[1]["restDays"], dumped[2]["restDays"]) == ([], None)


def test_nullable_fields_accept_null() -> None:
    model = AiCourseRequest.model_validate(_load("request_day_trip.json"))

    assert model.conditions.child_age_group is None
    assert model.rules.no_place_after is None
    street = model.candidates[2]
    assert (street.category, street.io, street.open_time) == (None, None, None)


def test_missing_nullable_fields_are_read_as_null() -> None:
    """Jackson record처럼 키가 빠진 nullable 필드는 null이다."""
    data = _request()
    del data["conditions"]["origin"]
    del data["conditions"]["childAgeGroup"]

    model = AiCourseRequest.model_validate(data)

    assert model.conditions.origin is None
    assert model.conditions.child_age_group is None


def test_item_stay_minutes_may_be_null() -> None:
    model = AiCourseResponse.model_validate(_load("response.json"))

    assert model.courses[0].days[0].items[1].stay_minutes is None


@pytest.mark.parametrize("violations", [None, "missing"])
def test_violations_default_to_empty_list(violations: str | None) -> None:
    data = _request()
    if violations == "missing":
        del data["violations"]
    else:
        data["violations"] = None

    model = AiCourseRequest.model_validate(data)

    assert model.violations == []
    assert model.model_dump(mode="json")["violations"] == []


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ((), "requestId"),
        (("conditions",), "startDate"),
        (("conditions",), "indoor"),
        (("rules",), "courses"),
        (("rules", "placesPerDay"), "min"),
    ],
)
def test_required_fields_are_enforced(path: tuple[str, ...], field: str) -> None:
    data = _request()
    target = data
    for key in path:
        target = target[key]
    del target[field]

    with pytest.raises(ValidationError):
        AiCourseRequest.model_validate(data)


def test_primitive_fields_reject_null() -> None:
    """Java 원시 타입(double·boolean)은 null이 될 수 없다."""
    with pytest.raises(ValidationError):
        Candidate.model_validate(_candidate(lat=None))
    with pytest.raises(ValidationError):
        Candidate.model_validate(_candidate(required=None))


# --- 모르는 필드 ---------------------------------------------------------------


def test_unknown_fields_are_ignored() -> None:
    data = _request(newTopLevel=1)
    data["conditions"]["accessibleOnly"] = True
    data["candidates"][0]["popularity"] = 10
    data["rules"]["placesPerDay"]["extra"] = "x"

    model = AiCourseRequest.model_validate(data)

    dumped = model.model_dump(mode="json")
    assert "newTopLevel" not in dumped
    assert "accessibleOnly" not in dumped["conditions"]
    assert "popularity" not in dumped["candidates"][0]


# --- 값 범위 ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "field", "value"),
    [
        (("conditions",), "companion", "family"),
        (("conditions",), "companion", "KIDS"),
        (("conditions",), "childAgeGroup", "elementary"),
        (("conditions",), "pace", "normal"),
        (("conditions",), "timeOfDay", "evening"),
    ],
)
def test_enum_like_values_are_checked(path: tuple[str, ...], field: str, value: str) -> None:
    data = _request()
    target = data
    for key in path:
        target = target[key]
    target[field] = value

    with pytest.raises(ValidationError):
        AiCourseRequest.model_validate(data)


@pytest.mark.parametrize(("field", "value"), [("io", "indoor"), ("restDays", ["MONDAY"])])
def test_candidate_enum_like_values_are_checked(field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        Candidate.model_validate(_candidate(**{field: value}))


# --- 헬퍼 ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "days"),
    [("request_day_trip.json", 1), ("request_kids_3days_required_festival.json", 3)],
)
def test_conditions_days(name: str, days: int) -> None:
    conditions = Conditions.model_validate(_load(name)["conditions"])

    assert conditions.days() == days


def test_candidate_runs_on() -> None:
    model = AiCourseRequest.model_validate(_load("request_kids_3days_required_festival.json"))
    palace, festival, _ = model.candidates

    assert festival.runs_on(date(2026, 12, 12))
    assert festival.runs_on(date(2026, 12, 21))
    assert not festival.runs_on(date(2026, 12, 11))
    assert not festival.runs_on(date(2026, 12, 22))
    assert palace.runs_on(date(2030, 1, 1))


def test_runs_on_is_true_when_only_one_event_date_is_known() -> None:
    candidate = Candidate.model_validate(_candidate(eventStartDate="2026-12-12"))

    assert candidate.runs_on(date(2026, 1, 1))


def test_with_violations_returns_copy() -> None:
    model = AiCourseRequest.model_validate(_request())

    retried = model.with_violations(["코스는 3개가 필요합니다."])

    assert retried.violations == ["코스는 3개가 필요합니다."]
    assert model.violations == []
    assert retried.candidates == model.candidates


def test_request_is_immutable() -> None:
    model = AiCourseRequest.model_validate(_request())

    with pytest.raises(ValidationError):
        model.request_id = 1  # type: ignore[misc]
