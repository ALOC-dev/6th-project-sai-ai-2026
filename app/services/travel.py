"""이동시간 계산 (가이드 5.2 ③, 6절).

- 직선 ≤ WALK_THRESHOLD_M: 도보 추정 (카카오 호출 없음)
- 직선 > WALK_THRESHOLD_M: 카카오 대중교통
- 같은 요청 안에서 같은 출발·도착 쌍은 한 번만 계산 (요청 범위 메모리 dict, 요청이 끝나면 버려짐)
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass

from app.clients.kakao import KakaoClient, KakaoError
from app.core.codes import PathSource, TransportMode
from app.core.constants import (
    MAX_KAKAO_CALLS_PER_REQUEST,
    TRANSIT_SPEED_M_PER_MIN,
    TRANSIT_WAIT_MINUTES,
    WALK_DETOUR_FACTOR,
    WALK_SPEED_M_PER_MIN,
    WALK_THRESHOLD_M,
)
from app.services.types import haversine_m

Point = tuple[float, float]  # (lat, lng)


class KakaoBudgetExceeded(KakaoError):
    """요청당 카카오 호출 상한(가이드 6절: 최악 6회)을 넘음. 그 후보만 건너뛴다."""


@dataclass(frozen=True)
class Leg:
    mode: TransportMode
    origin: Point
    dest: Point
    duration_seconds: int
    distance_m: int
    fare: int | None
    transfers: int | None
    route_summary: str | None
    path_source: PathSource
    path: list[list[float]]
    landing_url: str | None

    @property
    def minutes(self) -> int:
        """시각 계산용 분 단위 (올림)."""
        return math.ceil(self.duration_seconds / 60)


def walk_minutes_for(straight_m: float) -> float:
    return straight_m * WALK_DETOUR_FACTOR / WALK_SPEED_M_PER_MIN


def rough_minutes_for(straight_m: float) -> float:
    """하드 필터용 직선 기반 추정. 카카오를 부르지 않는다."""
    if straight_m <= WALK_THRESHOLD_M:
        return walk_minutes_for(straight_m)
    return TRANSIT_WAIT_MINUTES + straight_m * WALK_DETOUR_FACTOR / TRANSIT_SPEED_M_PER_MIN


def estimate_walk(origin: Point, dest: Point) -> Leg:
    straight = haversine_m(*origin, *dest)
    return Leg(
        mode=TransportMode.WALK,
        origin=origin,
        dest=dest,
        duration_seconds=int(round(walk_minutes_for(straight) * 60)),
        distance_m=int(round(straight * WALK_DETOUR_FACTOR)),
        fare=None,
        transfers=None,
        route_summary=None,
        path_source=PathSource.ESTIMATE,
        path=[[origin[0], origin[1]], [dest[0], dest[1]]],
        landing_url=None,
    )


class TravelService:
    """요청 하나에서만 쓰는 이동시간 계산기. 요청마다 새로 만든다."""

    def __init__(self, kakao: KakaoClient):
        self._kakao = kakao
        self._cache: dict[tuple[Point, Point], asyncio.Task[Leg]] = {}
        self.kakao_calls = 0

    async def leg(self, origin: Point, dest: Point, *, force_walk: bool = False) -> Leg:
        if force_walk or haversine_m(*origin, *dest) <= WALK_THRESHOLD_M:
            return estimate_walk(origin, dest)
        key = (origin, dest)
        task = self._cache.get(key)
        if task is None:
            if self.kakao_calls >= MAX_KAKAO_CALLS_PER_REQUEST:
                raise KakaoBudgetExceeded("kakao call budget exceeded")
            # 동시에 같은 구간을 요청해도 한 번만 부르도록 Task를 저장한다
            self.kakao_calls += 1
            task = asyncio.ensure_future(self._transit(origin, dest))
            self._cache[key] = task
        return await task

    async def aclose(self) -> None:
        """요청이 끝날 때 남은 호출을 정리한다 (응답 뒤에 계속 도는 작업 방지)."""
        for task in self._cache.values():
            if not task.done():
                task.cancel()
            elif not task.cancelled():
                task.exception()  # 꺼내 두지 않으면 "never retrieved" 경고가 남는다
        self._cache.clear()

    async def _transit(self, origin: Point, dest: Point) -> Leg:
        r = await self._kakao.public_transit(origin[0], origin[1], dest[0], dest[1])
        return Leg(
            mode=TransportMode.PUBLIC_TRANSIT,
            origin=origin,
            dest=dest,
            duration_seconds=r.duration_seconds,
            distance_m=r.distance_m,
            fare=r.fare,
            transfers=r.transfers,
            route_summary=r.route_summary,
            path_source=PathSource.KAKAO,
            path=r.path or [[origin[0], origin[1]], [dest[0], dest[1]]],
            landing_url=r.landing_url,
        )
