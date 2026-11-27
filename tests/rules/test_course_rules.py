"""코스 검증 규칙 테스트 (TRD 3.4).

1. Spring `CourseValidatorTest`(4건)를 옮긴다. Spring은 `anyMatch`로 일부만 보지만,
   여기서는 같은 단언에 더해 전체 목록도 확인한다
   (Spring이 재요청 때 보내는 문장과 순서가 같아야 하므로).
2. 위반 문장을 하나씩 일으켜 문장 전체를 확인한다.
"""

import json
from datetime import date, time
from pathlib import Path

from app.contract import AiCourseRequest, AiCourseResponse
from app.rules import validate
from tests.rules.helpers import (
    MONDAY,
    course,
    day,
    each_course,
    festival,
    place,
    request,
    response,
    three_of,
)

CONTRACT_FIXTURES = Path(__file__).parents[1] / "contract" / "fixtures"


# --- Spring CourseValidatorTest ------------------------------------------------


def test_valid() -> None:
    """CourseValidatorTest.valid: 규칙에 맞는 코스 3개는 위반이 없다."""
    req = request([place(1), place(2), place(3)], min_per_day=2, max_per_day=3)

    assert validate(req, three_of(day(1, 1, 2, 3))) == []


def test_shape_violations() -> None:
    """CourseValidatorTest.shapeViolations.

    코스 수·없는 id·중복·하루 장소 수·빠진 꼭 포함을 모두 위반으로 모은다.
    """
    req = request([place(1), place(2), place(3, required=True)], min_per_day=2, max_per_day=3)

    assert validate(req, response()) == ["코스는 3개가 필요합니다."]

    violations = validate(req, three_of(day(1, 1, 1, 99)))
    assert any("같은 장소가 두 번 들어갔습니다: 1" in v for v in violations)
    assert any("후보에 없는 장소입니다: 99" in v for v in violations)
    assert any("꼭 포함할 장소가 빠졌습니다: 3" in v for v in violations)
    assert violations == each_course(
        "같은 장소가 두 번 들어갔습니다: 1",
        "후보에 없는 장소입니다: 99",
        "꼭 포함할 장소가 빠졌습니다: 3",
    )

    violations = validate(req, three_of(day(1, 1)))
    assert any("1일차 장소는 2~3곳이어야 합니다 (1곳)." in v for v in violations)
    assert violations == each_course(
        "1일차 장소는 2~3곳이어야 합니다 (1곳).",
        "꼭 포함할 장소가 빠졌습니다: 3",
    )


def test_hours_and_dates() -> None:
    """CourseValidatorTest.hoursAndDates.

    영업시간·쉬는 요일·축제 기간은 위반이지만, 꼭 포함할 장소는 보지 않는다.
    """
    req = request(
        [
            place(1, "09:00", "10:30"),
            place(2, rest_days=["MON"]),
            festival(3, date(2026, 10, 30), date(2026, 11, 4)),
            festival(4, date(2026, 10, 30), date(2026, 11, 4), required=True),
        ],
        min_per_day=1,
        max_per_day=4,
    )

    violations = validate(req, three_of(day(1, 1, 2, 3, 4)))

    assert any(
        v.startswith("코스 1: 1 방문 시각 10:") and v.endswith("영업시간 09:00~10:30 밖입니다.")
        for v in violations
    )
    assert any("2는 2026-11-09(MONDAY)에 쉽니다." in v for v in violations)
    assert any("축제 3는 2026-11-09에 열리지 않습니다." in v for v in violations)
    assert not any(" 4" in v for v in violations)
    assert violations == each_course(
        "2는 2026-11-09(MONDAY)에 쉽니다.",
        "축제 3는 2026-11-09에 열리지 않습니다.",
        "1 방문 시각 10:02~11:32이 영업시간 09:00~10:30 밖입니다.",
    )


def test_kids_evening() -> None:
    """CourseValidatorTest.kidsEvening: 아이와 가면 20:00 넘어 끝나는 장소는 위반이다."""
    candidates = [place(1), place(2)]
    kids = request(candidates, kids=True, min_per_day=1, max_per_day=2, first_day_start=time(18, 0))

    violations = validate(kids, three_of(day(1, 1, 2)))
    assert any("아이와 가는 일정은 20:00 전에 끝나야 합니다: 2" in v for v in violations)
    assert violations == each_course("아이와 가는 일정은 20:00 전에 끝나야 합니다: 2")

    adults = request(candidates, min_per_day=1, max_per_day=2, first_day_start=time(18, 0))
    assert validate(adults, three_of(day(1, 1, 2))) == []


# --- 위반 문장 하나씩 ---------------------------------------------------------


def test_rule1_course_count() -> None:
    req = request([place(1)], min_per_day=1, max_per_day=1)
    one = course(day(1, 1))

    assert validate(req, response(one, one)) == ["코스는 3개가 필요합니다."]


def test_rule1_extra_courses_are_ignored() -> None:
    req = request([place(1)], min_per_day=1, max_per_day=1)
    one = course(day(1, 1))
    broken = course(day(1, 99))

    assert validate(req, response(one, one, one, broken)) == []


def test_rule2_day_number_out_of_range_or_repeated() -> None:
    req = request([place(1), place(2)], min_per_day=1, max_per_day=1, days=2)

    assert validate(req, three_of(day(1, 1), day(3, 2))) == each_course(
        "dayNumber는 1~2이 한 번씩 있어야 합니다."
    )
    assert validate(req, three_of(day(1, 1), day(1, 2))) == each_course(
        "dayNumber는 1~2이 한 번씩 있어야 합니다."
    )


def test_rule2_missing_day() -> None:
    req = request([place(1)], min_per_day=1, max_per_day=1, days=2)

    assert validate(req, three_of(day(1, 1))) == each_course("날짜 2일이 모두 있어야 합니다.")


def test_rule2_stops_course_check_but_not_other_courses() -> None:
    req = request([place(1)], min_per_day=1, max_per_day=1)
    good = course(day(1, 1))
    bad = course(day(2, 99))

    assert validate(req, response(good, bad, good)) == [
        "코스 2: dayNumber는 1~1이 한 번씩 있어야 합니다."
    ]


def test_rule3_places_per_day() -> None:
    req = request([place(1), place(2), place(3), place(4)], min_per_day=2, max_per_day=3)

    assert validate(req, three_of(day(1, 1, 2, 3, 4))) == each_course(
        "1일차 장소는 2~3곳이어야 합니다 (4곳)."
    )


def test_rule4_unknown_place() -> None:
    req = request([place(1)], min_per_day=1, max_per_day=2)

    assert validate(req, three_of(day(1, 1, 999))) == each_course("후보에 없는 장소입니다: 999")


def test_rule5_duplicate_across_days() -> None:
    req = request([place(1), place(2)], min_per_day=1, max_per_day=1, days=2)

    assert validate(req, three_of(day(1, 1), day(2, 1))) == each_course(
        "같은 장소가 두 번 들어갔습니다: 1"
    )


def test_rule6_required_missing() -> None:
    req = request([place(1), place(2, required=True)], min_per_day=1, max_per_day=1)

    assert validate(req, three_of(day(1, 1))) == each_course("꼭 포함할 장소가 빠졌습니다: 2")


def test_rule7_festival_out_of_period() -> None:
    req = request(
        [festival(1, date(2026, 11, 10), date(2026, 11, 12))], min_per_day=1, max_per_day=1
    )

    assert validate(req, three_of(day(1, 1))) == each_course(
        "축제 1는 2026-11-09에 열리지 않습니다."
    )


def test_rule7_festival_on_last_day_of_period_is_ok() -> None:
    req = request([festival(1, date(2026, 11, 1), MONDAY)], min_per_day=1, max_per_day=1)

    assert validate(req, three_of(day(1, 1))) == []


def test_rule8_rest_day() -> None:
    """TRD 3.4 예: 2026-12-21은 월요일이다."""
    req = request(
        [place(126508, rest_days=["MON", "SUN"])],
        min_per_day=1,
        max_per_day=1,
        start_date=date(2026, 12, 21),
        origin=None,
    )

    assert validate(req, three_of(day(1, 126508))) == each_course(
        "126508는 2026-12-21(MONDAY)에 쉽니다."
    )


def test_rule8_unknown_rest_days_are_not_checked() -> None:
    candidate = place(1)
    candidate["restDays"] = None
    req = request([candidate], min_per_day=1, max_per_day=1)

    assert validate(req, three_of(day(1, 1))) == []


def test_rule9_kids_end_after_20() -> None:
    req = request([place(1)], kids=True, min_per_day=1, max_per_day=1, first_day_start=time(19, 0))

    assert validate(req, three_of(day(1, 1))) == each_course(
        "아이와 가는 일정은 20:00 전에 끝나야 합니다: 1"
    )


def test_rule9_applies_to_required_place() -> None:
    req = request(
        [place(1, required=True)],
        kids=True,
        min_per_day=1,
        max_per_day=1,
        first_day_start=time(19, 0),
    )

    assert validate(req, three_of(day(1, 1))) == each_course(
        "아이와 가는 일정은 20:00 전에 끝나야 합니다: 1"
    )


def test_rule10_outside_hours() -> None:
    req = request(
        [place(1, "09:00", "18:00")], min_per_day=1, max_per_day=1, first_day_start=time(17, 0)
    )

    # 17:00 + 이동 2분 → 17:02~18:32
    violations = validate(req, three_of(day(1, 1)))
    assert violations == each_course("1 방문 시각 17:02~18:32이 영업시간 09:00~18:00 밖입니다.")


def test_rule10_after_last_entry() -> None:
    req = request(
        [place(1, "09:00", "18:00", "10:00")],
        min_per_day=1,
        max_per_day=1,
    )

    assert validate(req, three_of(day(1, 1, stay=60))) == each_course(
        "1 방문 시각 10:02~11:02이 영업시간 09:00~18:00 밖입니다."
    )


def test_rule10_before_open() -> None:
    req = request([place(1, "11:00", "18:00")], min_per_day=1, max_per_day=1)

    assert validate(req, three_of(day(1, 1))) == each_course(
        "1 방문 시각 10:02~11:32이 영업시간 11:00~18:00 밖입니다."
    )


def test_rule10_shows_clamped_time_past_midnight() -> None:
    req = request(
        [place(1, "09:00", "23:00")],
        min_per_day=1,
        max_per_day=1,
        first_day_start=time(22, 30),
    )

    assert validate(req, three_of(day(1, 1))) == each_course(
        "1 방문 시각 22:32~23:59이 영업시간 09:00~23:00 밖입니다."
    )


def test_rule10_skips_unknown_and_overnight_hours_and_required() -> None:
    req = request(
        [
            place(1, "09:00", None),
            place(2, "22:00", "02:00"),
            place(3, "09:00", "10:00", required=True),
        ],
        min_per_day=3,
        max_per_day=3,
    )

    assert validate(req, three_of(day(1, 1, 2, 3))) == []


def test_rule10_uses_lunch_and_previous_day_last_place() -> None:
    """둘째 날은 전날 마지막 장소에서 출발하고, 식사 칸이 다음 장소 시각을 민다."""
    req = request(
        [place(1), place(2), place(3, "09:00", "12:00")],
        min_per_day=1,
        max_per_day=2,
        days=2,
        later_day_start=time(9, 0),
    )

    # 둘째 날: 9:00 + (2→3 이동 2분) = 9:02 시작, 180분 머물면 12:02에 끝난다
    violations = validate(req, three_of(day(1, 1, 2), day(2, 3, stay=180)))
    assert violations == each_course("3 방문 시각 09:02~12:02이 영업시간 09:00~12:00 밖입니다.")


def test_stay_out_of_range_counts_as_90_minutes() -> None:
    req = request([place(1, "09:00", "11:31")], min_per_day=1, max_per_day=1)

    # 301분은 90분으로 본다: 10:02~11:32
    assert validate(req, three_of(day(1, 1, stay=301))) == each_course(
        "1 방문 시각 10:02~11:32이 영업시간 09:00~11:31 밖입니다."
    )
    assert validate(req, three_of(day(1, 1, stay=None))) == each_course(
        "1 방문 시각 10:02~11:32이 영업시간 09:00~11:31 밖입니다."
    )


def test_contract_fixture_request() -> None:
    """계약 예시(2박 3일, 아이 동반, 꼭 포함, 축제)와 예시 응답(코스 1개)."""
    req = AiCourseRequest.model_validate_json(
        (CONTRACT_FIXTURES / "request_kids_3days_required_festival.json").read_text(
            encoding="utf-8"
        )
    )
    data = json.loads((CONTRACT_FIXTURES / "response.json").read_text(encoding="utf-8"))
    res = AiCourseResponse.model_validate(data)

    assert validate(req, res) == ["코스는 3개가 필요합니다."]

    # 예시 코스를 3번 쓰면 3일차가 빠진다
    res3 = AiCourseResponse.model_validate({"courses": data["courses"] * 3})
    assert validate(req, res3) == each_course("날짜 3일이 모두 있어야 합니다.")
