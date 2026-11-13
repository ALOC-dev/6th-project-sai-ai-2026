from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.common import ErrorResponse
from app.schemas.feedback import FeedbackRequest
from app.services.preference import apply_feedback

router = APIRouter()


@router.post(
    "/feedback",
    status_code=204,
    response_class=Response,
    summary="사용자 피드백 수집",
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
def feedback(req: FeedbackRequest, request: Request, session: Session = Depends(get_session)) -> Response:
    apply_feedback(session, req, request.app.state.catalog)
    session.commit()
    return Response(status_code=204)
