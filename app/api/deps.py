import secrets
from collections.abc import Iterator

from fastapi import Header, Request
from sqlalchemy.orm import Session

from app.core.codes import ErrorCode
from app.core.errors import AppError


def verify_internal_key(
    request: Request,
    x_internal_api_key: str | None = Header(default=None, description="백엔드 ↔ AI 내부 인증 키"),
) -> None:
    expected: str = request.app.state.settings.internal_api_key
    # 서버에 키가 설정되지 않았으면 모든 요청을 거부한다 (실수로 열린 채 배포되는 것 방지)
    if not expected or not x_internal_api_key:
        raise AppError(401, ErrorCode.UNAUTHORIZED, "내부 API 키가 없거나 올바르지 않습니다.")
    if not secrets.compare_digest(x_internal_api_key.encode(), expected.encode()):
        raise AppError(401, ErrorCode.UNAUTHORIZED, "내부 API 키가 없거나 올바르지 않습니다.")


def get_session(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
