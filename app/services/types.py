"""알고리즘이 쓰는 메모리 속 장소 모델. DB와 분리해서 순수 함수 테스트가 쉽도록 한다."""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

import numpy as np

from app.core.codes import Category, Mood, SubType
from app.core.constants import CATEGORY_RULES, SUBTYPE_RULES, StayRule

EARTH_RADIUS_M = 6_371_000.0


@dataclass
class Place:
    place_id: int
    name: str
    category: Category
    latitude: float
    longitude: float
    price_min: int = 0
    price_max: int = 0
    moods: frozenset[Mood] = frozenset()
    sub_type: SubType | None = None
    road_address: str | None = None
    capacity: int | None = None
    stay_min_minutes: int | None = None
    kakao_place_id: str | None = None
    place_url: str | None = None
    rating_avg: float | None = None
    rating_count: int = 0
    # 요일(0=월) → (열림, 닫힘). 비어 있으면 항상 열림(산책로 등).
    hours: dict[int, tuple[time, time]] = field(default_factory=dict)

    @property
    def stay_rule(self) -> StayRule:
        """체류 규칙: 장소 stayMinMinutes → 세부 유형 → 카테고리 순."""
        base = CATEGORY_RULES[self.category]
        lo, hi, heavy = base.min_minutes, base.max_minutes, base.heavy
        if self.sub_type is not None:
            lo, hi, heavy = SUBTYPE_RULES[self.sub_type]
        if self.stay_min_minutes is not None:
            lo = self.stay_min_minutes
            hi = max(hi, lo)
        return StayRule(lo, hi, heavy, base.weight)

    def is_open_between(self, start: datetime, end: datetime) -> bool:
        """[start, end] 동안 계속 영업하는지. 자정을 넘기는 영업시간도 처리한다."""
        if not self.hours:
            return True
        # 전날 밤부터 이어지는 영업(예: 18:00~02:00)도 확인한다
        for day_offset in (0, -1):
            day = (start + timedelta(days=day_offset)).date()
            hours = self.hours.get(day.weekday())
            if hours is None:
                continue
            open_t, close_t = hours
            open_dt = datetime.combine(day, open_t)
            close_dt = datetime.combine(day, close_t)
            if close_dt <= open_dt:
                close_dt += timedelta(days=1)
            if open_dt <= start and end <= close_dt:
                return True
        return False


class PlaceCatalog:
    """서버 시작 시 장소 전체를 메모리에 올리고 numpy로 거리를 계산한다."""

    def __init__(self, places: list[Place]):
        self.places = list(places)
        self.by_id = {p.place_id: p for p in self.places}
        self.lat_rad = np.radians(np.array([p.latitude for p in self.places], dtype=float))
        self.lng_rad = np.radians(np.array([p.longitude for p in self.places], dtype=float))

    def __len__(self) -> int:
        return len(self.places)

    def distances_from(self, latitude: float, longitude: float) -> np.ndarray:
        """모든 장소까지의 직선거리(m), places와 같은 순서."""
        if not self.places:
            return np.zeros(0)
        lat0, lng0 = np.radians(latitude), np.radians(longitude)
        dlat = self.lat_rad - lat0
        dlng = self.lng_rad - lng0
        a = np.sin(dlat / 2) ** 2 + np.cos(lat0) * np.cos(self.lat_rad) * np.sin(dlng / 2) ** 2
        return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlat = p2 - p1
    dlng = np.radians(lng2 - lng1)
    a = np.sin(dlat / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlng / 2) ** 2
    return float(2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(min(1.0, max(0.0, a)))))


@dataclass(frozen=True)
class PersonalPrefs:
    """요청 사용자들의 개인 점수 평균과 행동 수 (가이드 5.3)."""

    scores: dict[int, float] = field(default_factory=dict)  # placeId → 참여자 평균 점수
    action_count: float = 0.0  # 참여자 평균 행동 수 n

    @property
    def alpha(self) -> float:
        from app.core.constants import PREF_ALPHA_K

        n = self.action_count
        return n / (n + PREF_ALPHA_K) if n > 0 else 0.0
