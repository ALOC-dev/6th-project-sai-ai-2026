"""DB 읽기·쓰기는 여기에 모은다. 카카오 결과는 절대 저장하지 않는다 (가이드 3절)."""

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.codes import Category, Mood, SubType
from app.db.models import (
    FeedbackEventRow,
    PlaceRow,
    RecommendationShownRow,
    UserPlacePrefRow,
)
from app.services.types import PersonalPrefs, Place


def row_to_place(row: PlaceRow) -> Place:
    return Place(
        place_id=row.place_id,
        name=row.name,
        category=Category(row.category_code),
        sub_type=SubType(row.sub_type) if row.sub_type else None,
        latitude=row.latitude,
        longitude=row.longitude,
        road_address=row.road_address,
        price_min=row.price_min,
        price_max=row.price_max,
        capacity=row.capacity,
        stay_min_minutes=row.stay_min_minutes,
        kakao_place_id=row.kakao_place_id,
        place_url=row.place_url,
        rating_avg=row.rating_avg,
        rating_count=row.rating_count,
        moods=frozenset(Mood(m.mood_code) for m in row.moods),
        hours={h.day_of_week: (h.open_time, h.close_time) for h in row.hours},
    )


def load_all_places(session: Session) -> list[Place]:
    rows = session.scalars(select(PlaceRow).order_by(PlaceRow.place_id)).all()
    return [row_to_place(r) for r in rows]


def load_personal_prefs(session: Session, user_ids: list[int]) -> PersonalPrefs:
    """참여자 개인 점수의 평균. 행동이 없는 장소는 0점으로 본다."""
    if not user_ids:
        return PersonalPrefs()
    rows = session.scalars(select(UserPlacePrefRow).where(UserPlacePrefRow.user_id.in_(user_ids))).all()
    totals: dict[int, float] = {}
    for r in rows:
        totals[r.place_id] = totals.get(r.place_id, 0.0) + r.score
    n_users = len(user_ids)
    scores = {pid: s / n_users for pid, s in totals.items()}
    # 행동 수 n: 장소 개수가 아니라 (요청, 행동 종류) 단위로 센다. 리롤 1번에 장소 6곳이어도 1회.
    actions = (
        select(FeedbackEventRow.user_id, FeedbackEventRow.request_id, FeedbackEventRow.type)
        .where(FeedbackEventRow.user_id.in_(user_ids))
        .distinct()
        .subquery()
    )
    action_total = session.scalar(select(func.count()).select_from(actions)) or 0
    return PersonalPrefs(scores=scores, action_count=action_total / n_users)


def record_shown(session: Session, request_id: int, shown: Iterable[tuple[int, int | None, bool]]) -> None:
    """보여준 장소 기록 (placeId, routeOrder, isMain). 미선택 감점·리롤 계산용."""
    for place_id, route_order, is_main in shown:
        session.add(
            RecommendationShownRow(
                request_id=request_id, place_id=place_id, route_order=route_order, is_main=is_main
            )
        )


def add_feedback_event(
    session: Session,
    *,
    user_id: int,
    request_id: int,
    type_: str,
    place_id: int,
    value: float | None,
    occurred_at: datetime,
) -> None:
    session.add(
        FeedbackEventRow(
            user_id=user_id,
            request_id=request_id,
            type=type_,
            place_id=place_id,
            value=value,
            occurred_at=occurred_at,
        )
    )


def add_pref_score(session: Session, user_id: int, place_id: int, delta: float, now: datetime) -> None:
    row = session.get(UserPlacePrefRow, (user_id, place_id))
    if row is None:
        row = UserPlacePrefRow(user_id=user_id, place_id=place_id, score=0.0, updated_at=now)
        session.add(row)
    row.score = (row.score or 0.0) + delta
    row.updated_at = now


def apply_rating(session: Session, place_id: int, rating: int) -> PlaceRow | None:
    row = session.get(PlaceRow, place_id)
    if row is None:
        return None
    count = row.rating_count or 0
    avg = row.rating_avg or 0.0
    row.rating_avg = (avg * count + rating) / (count + 1)
    row.rating_count = count + 1
    return row
