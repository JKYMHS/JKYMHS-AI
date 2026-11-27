"""서버 간 Bearer 인증 (TRD 3.1, 8).

Spring은 `Authorization: Bearer {AI_API_KEY}`를 보낸다. 키가 없거나 다르면 401.
설정의 `AI_API_KEY`가 비어 있으면 모든 요청을 거절한다(키 없이 열어 두지 않는다).
"""

import hmac
import logging

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.errors import ApiError
from app.config import Settings

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(message: str) -> ApiError:
    return ApiError(401, "UNAUTHORIZED", message, headers={"WWW-Authenticate": "Bearer"})


async def require_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
) -> None:
    """라우터에 붙이는 인증 의존성: `dependencies=[Depends(require_api_key)]`."""
    settings: Settings = request.app.state.settings
    expected = settings.ai_api_key.get_secret_value()
    if not expected:
        raise _unauthorized("서버에 API 키가 설정되지 않았습니다")
    if credentials is None:
        raise _unauthorized("Bearer 토큰이 필요합니다")
    if not hmac.compare_digest(credentials.credentials.encode(), expected.encode()):
        raise _unauthorized("API 키가 올바르지 않습니다")


def warn_if_api_key_missing(settings: Settings) -> None:
    """키가 비어 있으면 서버 시작 시 한 번 경고한다."""
    if not settings.ai_api_key.get_secret_value():
        logger.warning("AI_API_KEY가 비어 있어 인증이 필요한 요청을 모두 401로 거절합니다")
