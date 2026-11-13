"""build_routes(req, candidates) → 루트 routeCount개 (가이드 5.2).

DB는 부르지 않는다. 이동시간은 TravelService(요청 범위)로만 구한다.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.clients.kakao import KakaoError
from app.core.codes import ResultStatus, TransportMode
from app.core.constants import (
    BUFFER_MINUTES,
    CATEGORY_LABELS,
    MAX_HEAVY_SUM,
    MOOD_LABELS,
    SECOND_PLACE_MARGIN,
    SECOND_PLACE_PROB,
    SECOND_PLACE_RADIUS_M,
)
from app.schemas.recommendations import MoveSegment, RecommendationsRequest, Route, StaySegment
from app.services.recommend_places import ScoredPlace, available_minutes
from app.services.travel import KakaoBudgetExceeded, Leg, Point, TravelService, walk_minutes_for
from app.services.types import Place, PlaceCatalog, haversine_m


class PlaceNotFound(Exception):
    def __init__(self, place_id: int):
        super().__init__(f"placeId {place_id} 장소가 없습니다")
        self.place_id = place_id


@dataclass
class RoutePlan:
    places: list[Place]  # 방문 순서
    legs: list[Leg]  # 출발→1, (1→2), (마지막→도착)
    stays: list[int]  # 장소별 체류(분)


@dataclass
class BuildResult:
    status: ResultStatus
    routes: list[Route]
    shown: list[tuple[int, int | None, bool]]  # (placeId, routeOrder, isMain)


# ---------------------------------------------------------------- 체류 배분 (④)


def allocate_stays(places: list[Place], free_minutes: float) -> list[int] | None:
    """최소 체류를 먼저 주고, 남는 시간을 STAY_WEIGHT 비율로 나눈다.

    최대치를 넘으면 넘친 만큼 다른 장소로, 모두 차면 남는 시간은 복귀 여유로 돌린다.
    최소치를 못 채우면 None.
    """
    rules = [p.stay_rule for p in places]
    slack = free_minutes - sum(r.min_minutes for r in rules)
    if slack < 0:
        return None
    stays = [float(r.min_minutes) for r in rules]
    active = [i for i, r in enumerate(rules) if r.max_minutes > r.min_minutes]
    while slack > 1e-9 and active:
        wsum = sum(rules[i].weight for i in active)
        overflow = 0.0
        for i in active:
            new = stays[i] + slack * rules[i].weight / wsum
            if new > rules[i].max_minutes:
                overflow += new - rules[i].max_minutes
                new = float(rules[i].max_minutes)
            stays[i] = new
        slack = overflow
        active = [i for i in active if stays[i] < rules[i].max_minutes - 1e-9]
    return [int(s) for s in stays]  # 내림: 넘치지 않게


def min_stays(places: list[Place]) -> list[int]:
    return [p.stay_rule.min_minutes for p in places]


# ---------------------------------------------------------------- 시각 채우기 (⑤)


def stay_windows(req: RecommendationsRequest, legs: list[Leg], stays: list[int]) -> list[tuple[datetime, datetime]]:
    t = req.free_time_start_at
    windows = []
    for i, stay in enumerate(stays):
        t += timedelta(minutes=legs[i].minutes)
        windows.append((t, t + timedelta(minutes=stay)))
        t += timedelta(minutes=stay)
    return windows


def fits_hours(places: list[Place], windows: list[tuple[datetime, datetime]]) -> bool:
    return all(p.is_open_between(a, b) for p, (a, b) in zip(places, windows))


def finalize_plan(req: RecommendationsRequest, places: list[Place], legs: list[Leg]) -> RoutePlan | None:
    """체류를 배분하고 영업시간·복귀 시각을 확인한다. 안 맞으면 None."""
    t_minutes = available_minutes(req)
    move_total = sum(leg.minutes for leg in legs)
    free = t_minutes - move_total
    for stays in (allocate_stays(places, free), min_stays(places) if free >= sum(min_stays(places)) else None):
        if stays is None:
            continue
        windows = stay_windows(req, legs, stays)
        if not fits_hours(places, windows):
            continue  # 길게 배분해서 영업이 끝나면 최소 체류로 다시 시도
        return RoutePlan(places=places, legs=legs, stays=stays)
    return None


def to_route(req: RecommendationsRequest, plan: RoutePlan, route_order: int) -> Route:
    segments: list[StaySegment | MoveSegment] = []
    t = req.free_time_start_at
    seq = 1

    def add_move(leg: Leg) -> None:
        nonlocal t, seq
        segments.append(
            MoveSegment(
                seq=seq,
                transport_mode=leg.mode,
                from_latitude=leg.origin[0],
                from_longitude=leg.origin[1],
                to_latitude=leg.dest[0],
                to_longitude=leg.dest[1],
                duration_seconds=leg.duration_seconds,
                distance=leg.distance_m,
                fare=leg.fare,
                transfers=leg.transfers,
                route_summary=leg.route_summary,
                path_source=leg.path_source,
                path=leg.path,
                landing_url=leg.landing_url,
            )
        )
        t += timedelta(minutes=leg.minutes)
        seq += 1

    for i, (place, stay) in enumerate(zip(plan.places, plan.stays)):
        add_move(plan.legs[i])
        arrive = t
        t += timedelta(minutes=stay)
        segments.append(
            StaySegment(
                seq=seq,
                place_id=place.place_id,
                place_name=place.name,
                category_code=place.category,
                road_address_name=place.road_address,
                kakao_place_id=place.kakao_place_id,
                place_url=place.place_url,
                latitude=place.latitude,
                longitude=place.longitude,
                arrive_at=arrive,
                leave_at=t,
                price=place.price_min,
            )
        )
        seq += 1
    if len(plan.legs) > len(plan.places):  # 도착지로 돌아가는 MOVE
        add_move(plan.legs[-1])

    return_at = t
    buffer = int((req.free_time_end_at - return_at).total_seconds() // 60)
    price_min = sum(p.price_min for p in plan.places)
    price_max = sum(p.price_max for p in plan.places)
    return Route(
        route_order=route_order,
        main_place_count=len(plan.places),
        title=make_title(req, plan.places),
        reason=make_reason(req, plan, price_max, buffer),
        depart_at=req.free_time_start_at,
        return_at=return_at,
        buffer_minutes=buffer,
        price_min=price_min,
        price_max=price_max,
        segments=segments,
    )


def make_title(req: RecommendationsRequest, places: list[Place]) -> str:
    parts = []
    for p in places:
        mood = next((m for m in req.moods if m in p.moods), None)
        label = CATEGORY_LABELS[p.category]
        parts.append(f"{MOOD_LABELS[mood]} {label}" if mood else label)
    return " + ".join(parts)


def make_reason(req: RecommendationsRequest, plan: RoutePlan, price_max: int, buffer: int) -> str:
    move = sum(leg.minutes for leg in plan.legs)
    walk_only = all(leg.mode == TransportMode.WALK for leg in plan.legs)
    move_text = f"도보 {move}분" if walk_only else f"이동 {move}분(대중교통 포함)"
    price_text = "예산 안" if price_max <= req.max_price else "예산 일부 초과"
    return f"{move_text}, {price_text}, 여유 {buffer}분"


# ---------------------------------------------------------------- 메인 선정 (①)


def category_groups(req: RecommendationsRequest, candidates: list[ScoredPlace]) -> list[list[ScoredPlace]]:
    """요청 카테고리별 후보 목록. 각 카테고리 1등 점수가 높은 순으로 정렬한다."""
    groups: dict = {}
    for sp in candidates:
        if sp.place.category in req.categories:
            groups.setdefault(sp.place.category, []).append(sp)
    return sorted(groups.values(), key=lambda g: (-g[0].score, g[0].place.place_id))


# ---------------------------------------------------------------- 메인 2곳 (②)


def second_place_candidates(
    req: RecommendationsRequest,
    p1: Place,
    remaining: float,
    candidates: list[ScoredPlace],
    used_ids: set[int],
) -> list[Place]:
    """P1 반경 400m 안, heavy 합 ≤ MAX_HEAVY_SUM, 시간 식을 통과하는 P2 후보 (점수순)."""
    out = []
    heavy1 = p1.stay_rule.heavy
    walk400 = walk_minutes_for(SECOND_PLACE_RADIUS_M)
    for sp in candidates:
        p2 = sp.place
        if p2.place_id == p1.place_id or p2.place_id in used_ids:
            continue
        if haversine_m(p1.latitude, p1.longitude, p2.latitude, p2.longitude) > SECOND_PLACE_RADIUS_M:
            continue
        if heavy1 + p2.stay_rule.heavy > MAX_HEAVY_SUM:
            continue
        if remaining < SECOND_PLACE_MARGIN * (walk400 + p2.stay_rule.min_minutes):
            continue
        if p1.price_min + p2.price_min > req.max_price:
            continue
        out.append(p2)
    return out


async def plan_single(req: RecommendationsRequest, p1: Place, travel: TravelService) -> tuple[RoutePlan | None, float]:
    """메인 1곳 루트와 '남는시간'(2곳 판단용)을 함께 돌려준다."""
    start: Point = (req.start.latitude, req.start.longitude)
    here: Point = (p1.latitude, p1.longitude)
    if req.end is not None:
        go, back = await asyncio.gather(
            travel.leg(start, here), travel.leg(here, (req.end.latitude, req.end.longitude))
        )
        legs = [go, back]
    else:
        go = await travel.leg(start, here)
        back = None
        legs = [go]
    remaining = available_minutes(req) - go.minutes - p1.stay_rule.min_minutes - (back.minutes if back else 0)
    if remaining < 0:
        return None, remaining
    return finalize_plan(req, [p1], legs), remaining


async def plan_double(req: RecommendationsRequest, p1: Place, p2: Place, travel: TravelService) -> RoutePlan | None:
    """P2를 고른 뒤 실제 이동시간으로 다시 확인. 출발지에 가까운 곳을 먼저 간다."""
    s = req.start
    d1 = haversine_m(s.latitude, s.longitude, p1.latitude, p1.longitude)
    d2 = haversine_m(s.latitude, s.longitude, p2.latitude, p2.longitude)
    a, b = (p1, p2) if d1 <= d2 else (p2, p1)
    start: Point = (s.latitude, s.longitude)
    pa: Point = (a.latitude, a.longitude)
    pb: Point = (b.latitude, b.longitude)
    calls = [travel.leg(start, pa)]
    if req.end is not None:
        calls.append(travel.leg(pb, (req.end.latitude, req.end.longitude)))
    results = await asyncio.gather(*calls)
    middle = await travel.leg(pa, pb, force_walk=True)  # P1↔P2는 항상 도보 추정
    legs = [results[0], middle] + ([results[1]] if req.end is not None else [])
    return finalize_plan(req, [a, b], legs)


# ---------------------------------------------------------------- 전체


async def _try_single(req, place: Place, travel: TravelService, errors: list[KakaoError]):
    """메인 1곳 루트 시도. 카카오 오류면 그 후보만 건너뛰고 오류를 모아 둔다."""
    try:
        plan, remaining = await plan_single(req, place, travel)
    except KakaoError as e:
        errors.append(e)
        return None
    return (plan, remaining, place) if plan is not None else None


async def _first_success(req, group: list[ScoredPlace], travel, errors, taken: set[int]):
    """같은 카테고리 안에서 점수순으로 시도해, 처음 성공한 루트를 돌려준다."""
    for sp in group:
        if sp.place.place_id in taken:
            continue
        taken.add(sp.place.place_id)
        result = await _try_single(req, sp.place, travel, errors)
        if result is not None:
            return result, sp.score
    return None


async def _pick_mains_three(req, candidates, travel, errors) -> list[tuple[RoutePlan, float, Place]]:
    """routeCount=3: 서로 다른 카테고리에서 1곳씩(실패하면 같은 카테고리 다음 후보로 교체),
    카테고리가 모자라면 남은 후보로 채운다. 카테고리끼리는 동시에 계산한다."""
    groups = category_groups(req, candidates)
    taken: set[int] = set()
    found: list[tuple[tuple[RoutePlan, float, Place], float]] = []
    idx = 0
    while len(found) < req.route_count and idx < len(groups):
        batch = groups[idx: idx + (req.route_count - len(found))]
        idx += len(batch)
        results = await asyncio.gather(*(_first_success(req, g, travel, errors, taken) for g in batch))
        found.extend(r for r in results if r is not None)
    # 카테고리가 1~2개뿐이면 남은 후보로 채운다 (모두 메인 1곳)
    for sp in candidates:
        if len(found) >= req.route_count:
            break
        if sp.place.place_id in taken:
            continue
        taken.add(sp.place.place_id)
        result = await _try_single(req, sp.place, travel, errors)
        if result is not None:
            found.append((result, sp.score))
    found.sort(key=lambda x: (-x[1], x[0][2].place_id))  # routeOrder = 메인 점수순
    return [r for r, _ in found[: req.route_count]]


async def _try_double(req, p1: Place, p2: Place, travel: TravelService) -> RoutePlan | None:
    try:
        return await plan_double(req, p1, p2, travel)
    except KakaoError:
        return None  # 2곳 시도가 실패해도 이미 만든 1곳 루트는 그대로 쓴다


async def build_routes(
    req: RecommendationsRequest,
    candidates: list[ScoredPlace],
    catalog: PlaceCatalog,
    travel: TravelService,
) -> BuildResult:
    rng = random.Random(req.request_id)  # 재현·디버깅용 고정 시드
    errors: list[KakaoError] = []

    if req.route_count == 1:
        p1 = catalog.by_id.get(req.main_place_id)  # type: ignore[arg-type]
        if p1 is None:
            raise PlaceNotFound(req.main_place_id)  # type: ignore[arg-type]
        plan, remaining = await plan_single(req, p1, travel)  # 카카오 오류면 그대로 502
        plans = [(plan, remaining, p1)] if plan is not None else []
    else:
        plans = await _pick_mains_three(req, candidates, travel, errors)
    used = {p.place_id for plan, _, _ in plans for p in plan.places}

    # ② 메인 2곳
    if req.route_count == 1 and plans:
        plan, remaining, p1 = plans[0]
        # 첫 P2가 실제 시간·영업시간에서 걸리면 다음 후보까지 최대 3곳 시도 (P1↔P2는 도보 추정이라 추가 호출 거의 없음)
        for p2 in second_place_candidates(req, p1, remaining, candidates, used)[:3]:
            double = await _try_double(req, p1, p2, travel)
            if double is not None:
                plans[0] = (double, remaining, p1)
                break
    elif req.route_count == 3 and len(req.categories) >= 3 and plans:
        eligible = []
        for idx, (plan, remaining, p1) in enumerate(plans):
            options = second_place_candidates(req, p1, remaining, candidates, used)
            if options:
                eligible.append((idx, options[0]))
        if eligible and rng.random() < SECOND_PLACE_PROB:
            idx, p2 = rng.choice(eligible)
            plan, remaining, p1 = plans[idx]
            double = await _try_double(req, p1, p2, travel)
            if double is not None:
                plans[idx] = (double, remaining, p1)

    # 루트를 하나도 못 만들었고 원인이 카카오 오류라면 502 (호출 상한 초과만 있었으면 NO_RESULT)
    real_errors = [e for e in errors if not isinstance(e, KakaoBudgetExceeded)]
    if not plans and real_errors:
        raise real_errors[0]

    routes = [to_route(req, plan, i + 1) for i, (plan, _, _) in enumerate(plans)]
    for r in routes:
        assert_route_timing(req, r)
    shown = [(seg.place_id, r.route_order, True) for r in routes for seg in r.segments if isinstance(seg, StaySegment)]

    if not routes:
        status = ResultStatus.NO_RESULT
    elif len(routes) == req.route_count:
        status = ResultStatus.DONE
    else:
        status = ResultStatus.PARTIAL
    return BuildResult(status=status, routes=routes, shown=shown)


def assert_route_timing(req: RecommendationsRequest, route: Route) -> None:
    """도착이 공강 끝 − 15분 이내인지(end가 null이면 공강 끝 이내인지) 확인. 어기면 버그다."""
    limit = req.free_time_end_at - (timedelta(minutes=BUFFER_MINUTES) if req.end is not None else timedelta())
    if route.return_at > limit:
        raise RuntimeError(f"route {route.route_order} returns after limit")
