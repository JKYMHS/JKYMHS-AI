"""`POST /v1/courses` (TRD 3). Spring만 호출한다.

요청 본문과 출발지 좌표는 로그에 남기지 않는다 (TRD 8). 개수만 남긴다.
"""

import logging

from fastapi import APIRouter, Depends, Request

from app.api.auth import require_api_key
from app.api.errors import ApiError
from app.compose import compose
from app.config import Settings
from app.contract import AiCourseRequest, AiCourseResponse
from app.logging import bind_request_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


@router.post("/courses", response_model=AiCourseResponse)
async def create_courses(body: AiCourseRequest, request: Request) -> AiCourseResponse:
    bind_request_id(body.request_id)
    if not body.candidates:
        raise ApiError(422, "NO_CANDIDATES", "후보 장소가 없습니다")

    settings: Settings = request.app.state.settings
    response = await compose(body, reason_max_chars=settings.reason_max_chars)
    logger.info(
        "courses composed",
        extra={
            "candidates": len(body.candidates),
            "days": body.conditions.days(),
            "courses": len(response.courses),
            "places": [sum(len(d.items) for d in c.days) for c in response.courses],
            "retry": bool(body.violations),
        },
    )
    return response
