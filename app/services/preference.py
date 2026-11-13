"""피드백 → 개인 선호도 반영 (가이드 5.3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.codes import FeedbackType
from app.core.constants import PREF_REROLL, PREF_SELECT
from app.db import repository
from app.schemas.feedback import FeedbackRequest
from app.services.types import PlaceCatalog

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(KST).replace(tzinfo=None, microsecond=0)


def score_delta(req: FeedbackRequest) -> float | None:
    """장소 1곳당 점수 변화. None이면 기록만 하고 점수는 바꾸지 않는다."""
    if req.type == FeedbackType.SELECT:
        # 채팅방에서 장소 2곳 이상인 루트를 고른 경우는 반영하지 않는다
        return PREF_SELECT if len(req.place_ids) == 1 else None
    if req.type == FeedbackType.REROLL:
        return PREF_REROLL
    if req.type == FeedbackType.RATING:
        return (req.rating - 3) * 2  # type: ignore[operator]
    return None


def apply_feedback(session: Session, req: FeedbackRequest, catalog: PlaceCatalog) -> None:
    """원본 로그(feedback_events)를 남기고 개인 점수를 갱신한다. 커밋은 호출한 쪽이 한다.

    "보여줬는데 선택 안 한 루트 −0.5"는 적용 시점이 아직 정해지지 않아 여기서는 하지 않는다
    (recommendation_shown에 기록은 남아 있음).
    """
    now = now_kst()
    delta = score_delta(req)
    for user_id in req.user_ids:
        for place_id in req.place_ids:
            repository.add_feedback_event(
                session,
                user_id=user_id,
                request_id=req.request_id,
                type_=req.type.value,
                place_id=place_id,
                value=float(req.rating) if req.rating is not None else delta,
                occurred_at=req.occurred_at,
            )
            if delta is not None and place_id in catalog.by_id:
                repository.add_pref_score(session, user_id, place_id, delta, now)

    if req.type == FeedbackType.RATING:
        place_id = req.place_ids[0]
        # 별점은 사용자마다 한 번씩 장소 평점에 반영
        row = None
        for _ in req.user_ids:
            row = repository.apply_rating(session, place_id, req.rating)  # type: ignore[arg-type]
        place = catalog.by_id.get(place_id)
        if row is not None and place is not None:
            place.rating_avg = row.rating_avg
            place.rating_count = row.rating_count
