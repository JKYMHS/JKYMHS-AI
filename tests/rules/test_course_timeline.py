"""시각 계산 테스트.

Spring `CourseTimelineTest`(5건)를 그대로 옮기고, 이동 시간 어림(`RouteService.estimate`)과
공개 함수 `course_timeline`을 확인한다.
"""

from datetime import date, time
from typing import Any

from app.contract import Course
from app.rules import MealSlot, MealType, PlaceSlot, course_timeline
from app.rules.course_rules import _distance_meters, _estimate_minutes, _layout, _to_time
from tests.rules.helpers import MONDAY, course, day, place, request

# --- Spring CourseTimelineTest ------------------------------------------------


def test_lunch_after_place() -> None:
    """CourseTimelineTest.lunchAfterPlace: 앞 장소가 11:30~12:30에 끝나면 바로 점심."""
    slots = _layout(time(10, 0), [100, 60], [10, 5])

    assert slots == [
        PlaceSlot(0, 610, 710),
        MealSlot(MealType.LUNCH, 710, 770),
        PlaceSlot(1, 775, 835),
    ]


def test_lunch_before_long_place() -> None:
    """CourseTimelineTest.lunchBeforeLongPlace: 다음 장소를 다녀오면 12:30을 넘기면 11:30에 점심."""
    slots = _layout(time(9, 0), [120, 120], [0, 10])

    assert slots[1] == MealSlot(MealType.LUNCH, 690, 750)
    assert slots[2] == PlaceSlot(1, 760, 880)


def test_dinner_at_end() -> None:
    """CourseTimelineTest.dinnerAtEnd: 마지막 장소 뒤가 창 안이면 끝에 저녁."""
    slots = _layout(time(15, 0), [90, 60], [0, 0])

    assert slots == [
        PlaceSlot(0, 900, 990),
        PlaceSlot(1, 990, 1050),
        MealSlot(MealType.DINNER, 1050, 1110),
    ]


def test_no_meal_when_day_ends_early() -> None:
    """CourseTimelineTest.noMealWhenDayEndsEarly: 식사 창 전에 끝나면 식사 칸 없음."""
    assert _layout(time(9, 0), [60], [0]) == [PlaceSlot(0, 540, 600)]


def test_past_midnight() -> None:
    """CourseTimelineTest.pastMidnight.

    분은 자정을 넘겨도 돌아가지 않고, 화면 시각은 23:59에서 멈춘다.
    """
    slots = _layout(time(22, 0), [180], [0])

    assert slots[0].end == 25 * 60
    assert _to_time(25 * 60) == time(23, 59)


# --- 추가: 시각 계산 ----------------------------------------------------------


def test_empty_day_has_no_slots() -> None:
    assert _layout(time(9, 0), [], []) == []


def test_lunch_and_dinner_both_inserted_once() -> None:
    slots = _layout(time(10, 0), [90, 300, 60], [0, 0, 0])

    assert [s for s in slots if isinstance(s, MealSlot)] == [
        MealSlot(MealType.LUNCH, 690, 750),
        MealSlot(MealType.DINNER, 1050, 1110),
    ]


# --- 추가: RouteService.estimate ---------------------------------------------


def test_distance_is_haversine_rounded() -> None:
    # 위도 0.001도 ≈ 111.195m, 0.1도 ≈ 11119.49m
    assert _distance_meters(37.57, 126.977, 37.571, 126.977) == 111
    assert _distance_meters(37.57, 126.977, 37.67, 126.977) == 11119


def test_estimate_walks_up_to_1km_at_4kmh() -> None:
    assert _estimate_minutes(37.57, 126.977, 37.571, 126.977) == 2  # ceil(111 / 66.67)
    assert _estimate_minutes(37.57, 126.977, 37.5789, 126.977) == 15  # 990m, ceil(990 / 66.67)


def test_estimate_drives_over_1km_at_30kmh() -> None:
    assert _estimate_minutes(37.57, 126.977, 37.579, 126.977) == 3  # 1000.75m → 1001m, 자동차
    assert _estimate_minutes(37.57, 126.977, 37.67, 126.977) == 23  # ceil(11119 / 500)


def test_estimate_is_at_least_one_minute() -> None:
    assert _estimate_minutes(37.57, 126.977, 37.57, 126.977) == 1


# --- 추가: course_timeline -----------------------------------------------------


def test_course_timeline_carries_origin_and_day_start() -> None:
    """첫날은 출발지·요청 시작 시각, 둘째 날은 전날 마지막 장소·취향 시간대에서 시작한다."""
    req = request(
        [place(1), place(2), place(3)],
        min_per_day=1,
        max_per_day=2,
        days=2,
        first_day_start=time(13, 0),
        later_day_start=time(9, 0),
    )

    timelines = course_timeline(req, _course_of(day(2, 3), day(1, 1, 2)))

    first, second = timelines
    assert (first.day_number, first.date, first.day_start) == (1, MONDAY, time(13, 0))
    assert first.content_ids == [1, 2]
    assert first.move_minutes == [2, 2]  # 출발지→1 111m, 1→2 111m
    assert first.slots == [PlaceSlot(0, 782, 872), PlaceSlot(1, 874, 964)]
    assert (second.day_number, second.date, second.day_start) == (2, date(2026, 11, 10), time(9, 0))
    assert second.move_minutes == [2]  # 전날 마지막 장소 2 → 3
    assert second.slots == [PlaceSlot(0, 542, 632)]


def test_course_timeline_skips_unknown_and_duplicate_and_fixes_stay() -> None:
    req = request([place(1), place(2)], min_per_day=1, max_per_day=3)

    (timeline,) = course_timeline(req, _course_of(day(1, 1, 99, 1, 2, stay=10)))

    assert timeline.content_ids == [1, 2]
    assert timeline.stay_minutes == [90, 90]  # 30분 미만은 90분


def test_course_timeline_without_origin_starts_with_zero_move() -> None:
    req = request([place(1)], min_per_day=1, max_per_day=1, origin=None)

    (timeline,) = course_timeline(req, _course_of(day(1, 1)))

    assert timeline.move_minutes == [0]
    # 11:30에 끝나 점심 창 안이므로 끝에 점심이 붙는다
    assert timeline.slots == [PlaceSlot(0, 600, 690), MealSlot(MealType.LUNCH, 690, 750)]


def _course_of(*days: dict[str, Any]) -> Course:
    return Course.model_validate(course(*days))
