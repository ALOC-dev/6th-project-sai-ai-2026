"""카카오 길찾기 호출은 이 모듈 한 곳에만 둔다 (가이드 10절).

- 결과는 저장·캐싱하지 않는다. 같은 요청 안의 메모리 재사용은 services/travel.py가 맡는다.
- 테스트는 항상 MockKakaoClient를 쓴다.
- 실제 호출(RealKakaoClient)의 요청 파라미터·응답 필드는 실제 키로 확인한 뒤 확정한다 (뼈대 단계 TODO).
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.constants import KAKAO_TIMEOUT_SECONDS

logger = logging.getLogger("sai_ai.kakao")

PUBLIC_TRANSIT_URL = "https://dapi.kakao.com/v2/routing/publictraffic"


class KakaoError(Exception):
    """카카오 호출 실패. API 계층에서 502 EXTERNAL_API_ERROR로 바꾼다."""


@dataclass(frozen=True)
class TransitResult:
    duration_seconds: int
    distance_m: int
    fare: int | None
    transfers: int | None
    route_summary: str | None
    path: list[list[float]]  # [[lat, lng], ...]
    landing_url: str | None


class KakaoClient(Protocol):
    async def public_transit(
        self, from_lat: float, from_lng: float, to_lat: float, to_lng: float
    ) -> TransitResult: ...

    async def aclose(self) -> None: ...


class RealKakaoClient:
    def __init__(self, rest_api_key: str, timeout: float = KAKAO_TIMEOUT_SECONDS):
        if not rest_api_key:
            raise ValueError("KAKAO_REST_API_KEY가 설정되지 않았습니다")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"KakaoAK {rest_api_key}"},
        )

    async def public_transit(self, from_lat, from_lng, to_lat, to_lng) -> TransitResult:
        # TODO(실제 키로 확인): 파라미터 이름과 좌표 순서(경도,위도)
        params = {"origin": f"{from_lng},{from_lat}", "destination": f"{to_lng},{to_lat}"}
        try:
            resp = await self._client.get(PUBLIC_TRANSIT_URL, params=params)
        except httpx.TimeoutException as e:
            raise KakaoError("kakao timeout") from e
        except httpx.HTTPError as e:
            raise KakaoError("kakao connection error") from e
        if resp.status_code != 200:
            # 응답 본문에 키가 섞일 일은 없지만, 로그에는 상태 코드만 남긴다.
            logger.warning("kakao public transit failed: status=%s", resp.status_code)
            raise KakaoError(f"kakao status {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as e:
            raise KakaoError("kakao returned non-JSON body") from e
        return parse_public_transit(data)

    async def aclose(self) -> None:
        await self._client.aclose()


def _int_or_none(v) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, dict):  # 예: {"total": 1500}
        return _int_or_none(v.get("total") or v.get("value"))
    if isinstance(v, str) and v.strip().isdigit():
        return int(v)
    return None


def parse_public_transit(data) -> TransitResult:
    """routes[0]만 쓴다. 필드 이름은 가이드 3절 기준이며 실제 응답으로 확인 필요.

    응답 모양이 예상과 다르면 어떤 예외든 KakaoError로 바꿔 502로 처리되게 한다.
    """
    try:
        return _parse_public_transit(data)
    except KakaoError:
        raise
    except Exception as e:  # noqa: BLE001 - 외부 응답 형식 오류는 모두 502
        raise KakaoError("unexpected kakao response") from e


def _parse_public_transit(data) -> TransitResult:
    routes = data.get("routes") or []
    if not routes:
        raise KakaoError("no route")
    r = routes[0]
    points: list[list[float]] = []
    for section in r.get("sections") or [r]:
        path = section.get("path") or {}
        for pt in path.get("points") or []:
            if isinstance(pt, dict) and "y" in pt and "x" in pt:
                points.append([float(pt["y"]), float(pt["x"])])
            elif isinstance(pt, (list, tuple)) and len(pt) == 2:
                points.append([float(pt[0]), float(pt[1])])
    total_time = _int_or_none(r.get("totalTime"))
    if total_time is None or total_time <= 0:
        raise KakaoError("missing totalTime")
    summary = r.get("summary")
    landing = r.get("landingURL")
    return TransitResult(
        duration_seconds=total_time,
        distance_m=_int_or_none(r.get("totalDistance")) or 0,
        fare=_int_or_none(r.get("fare")),
        transfers=_int_or_none(r.get("transfers")),
        route_summary=summary if isinstance(summary, str) else None,
        path=points,
        landing_url=landing if isinstance(landing, str) and landing.startswith("https://") else None,
    )


class MockKakaoClient:
    """카카오를 부르지 않는 가짜 클라이언트. 직선거리로 그럴듯한 값을 만든다."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        # 테스트 확인용. 오래 띄워 둬도 메모리가 늘지 않게 최근 1000건만 둔다.
        self.calls: deque[tuple[float, float, float, float]] = deque(maxlen=1000)

    async def public_transit(self, from_lat, from_lng, to_lat, to_lng) -> TransitResult:
        from app.core.constants import TRANSIT_SPEED_M_PER_MIN, TRANSIT_WAIT_MINUTES
        from app.services.types import haversine_m

        self.calls.append((from_lat, from_lng, to_lat, to_lng))
        if self.fail:
            raise KakaoError("mock failure")
        dist = haversine_m(from_lat, from_lng, to_lat, to_lng)
        minutes = TRANSIT_WAIT_MINUTES + dist * 1.3 / TRANSIT_SPEED_M_PER_MIN
        return TransitResult(
            duration_seconds=int(round(minutes * 60)),
            distance_m=int(round(dist * 1.3)),
            fare=1500,
            transfers=0,
            route_summary="(mock) 버스",
            path=[[from_lat, from_lng], [to_lat, to_lng]],
            landing_url=None,
        )

    async def aclose(self) -> None:
        return None
