"""코스 구성 (TRD 5).

`compose(request)` 하나가 라우터와의 경계다. 지금은 LLM 없는 임시 구현(`nearest`, T1-4)이고,
LLM 구현(T3-7)은 이 함수의 안쪽만 바꾼다.
"""

from app.compose.nearest import load_texts, plan
from app.contract import AiCourseRequest, AiCourseResponse


async def compose(request: AiCourseRequest, *, reason_max_chars: int = 40) -> AiCourseResponse:
    """후보로 코스 `rules.courses`개를 짠다. `candidates`는 비어 있지 않아야 한다."""
    return plan(request, load_texts(), reason_max_chars=reason_max_chars)


__all__ = ["compose"]
