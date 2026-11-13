"""recommend_places(req) → 후보 장소 목록 (가이드 5.1).

순수 함수: DB·카카오를 부르지 않는다. 장소 목록(catalog)과 개인 선호(prefs)를 인자로 받는다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta

from app.core.constants import BUFFER_MINUTES, DEFAULT_RATING, PREF_SCALE, SCORE_WEIGHTS
from app.schemas.common import CommonRequest
from app.services.travel import rough_minutes_for
from app.services.types import PersonalPrefs, Place, PlaceCatalog, haversine_m


@dataclass(frozen=True)
class ScoredPlace:
    place: Place
    distance_m: float  # 출발지 직선거리
    score: float


def available_minutes(req: CommonRequest) -> float:
    """T = (공강 끝 − BUFFER) − 공강 시작. 다음 수업이 없으면(end=null) BUFFER는 0."""
    buffer = BUFFER_MINUTES if req.end is not None else 0
    return (req.free_time_end_at - req.free_time_start_at).total_seconds() / 60 - buffer


def return_minutes(place: Place, req: CommonRequest) -> float:
    if req.end is None:
        return 0.0
    return rough_minutes_for(haversine_m(place.latitude, place.longitude, req.end.latitude, req.end.longitude))


def passes_hard_filter(place: Place, distance_m: float, req: CommonRequest, t_minutes: float, excluded: set[int]) -> bool:
    if place.place_id in excluded:
        return False
    # 카테고리는 OR 선택: 요청한 카테고리 중 하나여야 한다 (판단 근거는 정리 문서 참고)
    if place.category not in req.categories:
        return False
    if distance_m > req.max_distance:
        return False
    # 1인 가격: 가장 싼 선택지(priceMin)가 예산 안이면 통과 (판단 근거는 정리 문서 참고)
    if place.price_min > req.max_price:
        return False
    if place.capacity is not None and place.capacity < req.headcount:
        return False
    go = rough_minutes_for(distance_m)
    min_stay = place.stay_rule.min_minutes
    if go + min_stay + return_minutes(place, req) > t_minutes:
        return False
    # 영업시간: 도착부터 최소 체류가 끝날 때까지 열려 있어야 한다
    arrive = req.free_time_start_at + timedelta(minutes=go)
    if not place.is_open_between(arrive, arrive + timedelta(minutes=min_stay)):
        return False
    return True


def base_score(place: Place, distance_m: float, req: CommonRequest) -> float:
    """w1×분위기 + w2×카테고리 + w3×평점 + w4×가격 여유 − w5×이동거리. 각 항은 0~1로 맞춘다."""
    w = SCORE_WEIGHTS
    mood = len(place.moods & set(req.moods)) / len(req.moods)
    category = 1.0 if place.category in req.categories else 0.0
    rating = (place.rating_avg if place.rating_avg is not None else DEFAULT_RATING) / 5.0
    price = (req.max_price - place.price_min) / req.max_price if req.max_price > 0 else 0.0
    price = min(1.0, max(0.0, price))
    dist = min(1.0, distance_m / req.max_distance)
    return w["mood"] * mood + w["category"] * category + w["rating"] * rating + w["price"] * price - w["distance"] * dist


def final_score(base: float, place_id: int, prefs: PersonalPrefs) -> float:
    """(1 − α) × 전체 점수 + α × 개인 점수. 개인 점수는 tanh로 -1~1에 맞춘다."""
    alpha = prefs.alpha
    if alpha == 0:
        return base
    personal = math.tanh(prefs.scores.get(place_id, 0.0) / PREF_SCALE)
    return (1 - alpha) * base + alpha * personal


def recommend_places(
    req: CommonRequest,
    catalog: PlaceCatalog,
    prefs: PersonalPrefs | None = None,
    limit: int | None = None,
) -> list[ScoredPlace]:
    prefs = prefs or PersonalPrefs()
    t_minutes = available_minutes(req)
    if t_minutes <= 0 or len(catalog) == 0:
        return []
    distances = catalog.distances_from(req.start.latitude, req.start.longitude)
    excluded = set(req.exclude_place_ids)
    scored: list[ScoredPlace] = []
    for place, d in zip(catalog.places, distances):
        d = float(d)
        if not passes_hard_filter(place, d, req, t_minutes, excluded):
            continue
        s = final_score(base_score(place, d, req), place.place_id, prefs)
        scored.append(ScoredPlace(place=place, distance_m=d, score=s))
    # 점수 내림차순, 같으면 가까운 순, 그다음 placeId (결과가 항상 같게)
    scored.sort(key=lambda sp: (-sp.score, sp.distance_m, sp.place.place_id))
    return scored[:limit] if limit is not None else scored
