"""`POST /v1/courses` 임시 구현 테스트 (T1-4, TRD 3·6).

요청 예시는 계약 테스트의 fixture(Spring 형식 JSON)를 쓴다.
"""

import copy
import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.compose.nearest import is_open_on, load_texts
from app.contract import AiCourseRequest, AiCourseResponse
from tests.api.conftest import client_for, make_app

KEY = "test-key-123"
AUTH = {"Authorization": f"Bearer {KEY}"}
FIXTURES = Path(__file__).parents[1] / "contract" / "fixtures"
REQUEST_FIXTURES = ["request_day_trip.json", "request_kids_3days_required_festival.json"]


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


def _candidate(content_id: int, i: int, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = copy.deepcopy(_load("request_day_trip.json")["candidates"][1])
    data.update(
        contentId=content_id,
        name=f"장소 {content_id}",
        lat=37.56 + 0.003 * (i % 7),
        lng=126.97 + 0.004 * (i // 7),
    )
    data.update(overrides)
    return data


def _many_candidates_request(count: int = 30, days: int = 2) -> dict[str, Any]:
    """후보가 넉넉한 요청: 여유(2–3곳), 꼭 포함 1곳, 쉬는 날·축제 섞음."""
    data = _load("request_day_trip.json")
    start = date(2026, 12, 20)  # 일요일
    data["conditions"].update(
        startDate=start.isoformat(),
        endDate=(start + timedelta(days=days - 1)).isoformat(),
        pace="relaxed",
    )
    data["rules"]["placesPerDay"] = {"min": 2, "max": 3}
    candidates = [_candidate(5000 + i, i) for i in range(count)]
    candidates[3]["required"] = True
    candidates[3]["restDays"] = ["SUN"]
    candidates[5]["restDays"] = ["SUN", "MON"]  # 기간 내내 쉼
    candidates[6].update(eventStartDate="2026-12-01", eventEndDate="2026-12-10")  # 끝난 축제
    candidates[7]["restDays"] = ["MON"]
    data["candidates"] = candidates
    return data


async def _post(body: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
    async with client_for(make_app(ai_api_key=KEY)) as client:
        return await client.post("/v1/courses", json=body, headers=headers or {})


def _check_course_rules(body: dict[str, Any], resp_json: dict[str, Any]) -> None:
    """Spring `CourseValidator` 규칙 1–8 중 이 구현이 지켜야 하는 것 (TRD 3.4)."""
    request = AiCourseRequest.model_validate(body)
    response = AiCourseResponse.model_validate(resp_json)
    by_id = {c.content_id: c for c in request.candidates}
    required = {c.content_id for c in request.candidates if c.required}
    n_days = request.conditions.days()

    assert len(response.courses) == request.rules.courses
    for course in response.courses:
        assert [d.day_number for d in course.days] == list(range(1, n_days + 1))
        ids = [item.content_id for d in course.days for item in d.items]
        assert set(ids) <= set(by_id), "후보 밖 장소"
        assert len(ids) == len(set(ids)), "한 코스 안에서 중복"
        assert required <= set(ids), "꼭 포함 장소 누락"
        for d in course.days:
            day = request.conditions.start_date + timedelta(days=d.day_number - 1)
            assert len(d.items) <= request.rules.places_per_day.max
            for item in d.items:
                candidate = by_id[item.content_id]
                if not candidate.required:
                    assert is_open_on(candidate, day), (item.content_id, day)


# --- 인증 ---------------------------------------------------------------------


async def test_missing_key_is_401() -> None:
    resp = await _post(_load("request_day_trip.json"))
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"


async def test_wrong_key_is_401() -> None:
    resp = await _post(_load("request_day_trip.json"), {"Authorization": "Bearer nope"})
    assert resp.status_code == 401


# --- 정상 요청 ----------------------------------------------------------------


async def test_day_trip_response_shape() -> None:
    resp = await _post(_load("request_day_trip.json"), AUTH)

    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {"courses"}
    titles = [c["title"] for c in data["courses"]]
    assert titles == ["인기 명소 코스", "여유로운 동선 코스", "숨은 명소 코스"]
    for course in data["courses"]:
        assert set(course) == {"title", "summary", "days"}
        assert 0 < len(course["summary"]) <= 40
        for day in course["days"]:
            assert set(day) == {"dayNumber", "items"}
            for item in day["items"]:
                assert set(item) == {"contentId", "stayMinutes", "reason"}
                assert item["stayMinutes"] == load_texts().stay_minutes
                assert 0 < len(item["reason"]) <= 40


async def test_day_trip_starts_nearest_to_origin() -> None:
    resp = await _post(_load("request_day_trip.json"), AUTH)
    # 출발지(37.5701, 126.9832)에서 가장 가까운 곳은 탑골공원(264337).
    first = resp.json()["courses"][0]["days"][0]["items"][0]
    assert first["contentId"] == 264337
    assert first["reason"] == "공원 · 인기 장소"


@pytest.mark.parametrize("name", REQUEST_FIXTURES)
async def test_fixture_requests_follow_rules(name: str) -> None:
    body = _load(name)
    resp = await _post(body, AUTH)
    assert resp.status_code == 200
    _check_course_rules(body, resp.json())


async def test_kids_trip_places_festival_and_rest_days() -> None:
    body = _load("request_kids_3days_required_festival.json")
    resp = await _post(body, AUTH)

    for course in resp.json()["courses"]:
        days = {item["contentId"]: d["dayNumber"] for d in course["days"] for item in d["items"]}
        # 꼭 포함(1001)은 모든 코스에. 축제(2830)는 12-21까지라 1–2일차,
        # 민속박물관은 화요일(3일차)만 연다.
        assert 1001 in days
        assert days.get(2830, 1) in (1, 2)
        assert days.get(126508, 3) == 3


async def test_few_candidates_keep_min_places_on_later_days() -> None:
    # 후보 3곳, 3일, 하루 1–2곳: 첫날을 2곳으로 채우면 하루가 빈다. 날마다 1곳씩 넣어야 한다.
    resp = await _post(_load("request_kids_3days_required_festival.json"), AUTH)

    for course in resp.json()["courses"]:
        assert [len(d["items"]) for d in course["days"]] == [1, 1, 1]


async def test_many_candidates_fill_places_per_day_range() -> None:
    body = _many_candidates_request()
    resp = await _post(body, AUTH)

    assert resp.status_code == 200
    data = resp.json()
    _check_course_rules(body, data)
    for course in data["courses"]:
        for day in course["days"]:
            assert 2 <= len(day["items"]) <= 3
        ids = {item["contentId"] for d in course["days"] for item in d["items"]}
        assert 5003 in ids
        assert 5005 not in ids  # 기간 내내 쉼
        assert 5006 not in ids  # 끝난 축제


async def test_courses_differ() -> None:
    resp = await _post(_many_candidates_request(), AUTH)
    sets = [
        frozenset(item["contentId"] for d in c["days"] for item in d["items"])
        for c in resp.json()["courses"]
    ]
    assert len(set(sets)) == 3


async def test_more_courses_than_titles() -> None:
    body = _many_candidates_request()
    body["rules"]["courses"] = 4
    resp = await _post(body, AUTH)
    assert [c["title"] for c in resp.json()["courses"]][3] == "추천 코스 4"


async def test_retry_with_violations_is_accepted() -> None:
    body = _load("request_kids_3days_required_festival.json")
    assert body["violations"]
    resp = await _post(body, AUTH)
    assert resp.status_code == 200


async def test_origin_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    body = _load("request_day_trip.json")
    await _post(body, AUTH)
    text = " ".join(f"{r.getMessage()} {vars(r)}" for r in caplog.records)
    assert "37.5701" not in text
    assert "126.9832" not in text
    assert any(getattr(r, "request_id", None) == 123 for r in caplog.records)


# --- 오류 ---------------------------------------------------------------------


async def test_no_candidates_is_422() -> None:
    body = _load("request_day_trip.json")
    body["candidates"] = []
    resp = await _post(body, AUTH)

    assert resp.status_code == 422
    assert resp.json() == {"code": "NO_CANDIDATES", "message": "후보 장소가 없습니다"}


async def test_invalid_body_is_422_invalid_request() -> None:
    body = _load("request_day_trip.json")
    del body["rules"]
    resp = await _post(body, AUTH)

    assert resp.status_code == 422
    assert resp.json()["code"] == "INVALID_REQUEST"
