from datetime import time

import pytest
from fastapi.testclient import TestClient

from app.clients.kakao import MockKakaoClient
from app.core.codes import Category, Mood, SubType
from app.core.config import Settings
from app.db.models import PlaceHourRow, PlaceMoodRow, PlaceRow
from app.main import create_app
from app.services.types import Place, PlaceCatalog
from scripts.seed_fake_places import offset

TEST_KEY = "test-internal-key"
CAMPUS = (37.5838, 127.0587)


def at(dist_m: float, bearing: float = 90.0) -> tuple[float, float]:
    """캠퍼스에서 dist_m 떨어진 좌표."""
    return offset(CAMPUS[0], CAMPUS[1], dist_m, bearing)


def make_place(place_id: int, category: Category, dist_m: float, bearing: float = 90.0, **kw) -> Place:
    lat, lng = at(dist_m, bearing)
    kw.setdefault("price_min", 5000)
    kw.setdefault("price_max", 8000)
    kw.setdefault("moods", frozenset({Mood.CALM}))
    return Place(place_id=place_id, name=f"P{place_id}", category=category, latitude=lat, longitude=lng, **kw)


def base_request(**overrides) -> dict:
    body = {
        "requestId": 100,
        "userIds": [1],
        "categories": ["CAFE"],
        "moods": ["CALM"],
        "headcount": 2,
        "maxPrice": 15000,
        "maxDistance": 2000,
        "freeTimeStartAt": "2026-11-16T12:00:00",  # 월요일
        "freeTimeEndAt": "2026-11-16T15:00:00",
        "start": {"name": "출발", "latitude": CAMPUS[0], "longitude": CAMPUS[1]},
        "end": {"name": "도착", "latitude": CAMPUS[0], "longitude": CAMPUS[1]},
        "excludePlaceIds": [],
    }
    body.update(overrides)
    return body


@pytest.fixture
def catalog_factory():
    return lambda places: PlaceCatalog(places)


# ------------------------------------------------------------ API 테스트용 앱


def _seed_rows(session):
    def row(pid, cat, dist, bearing=90, sub=None, moods=("CALM",), pmin=5000, pmax=8000, hours=(time(8), time(22)), cap=10):
        lat, lng = at(dist, bearing)
        r = PlaceRow(
            place_id=pid, name=f"장소{pid}", category_code=cat.value, sub_type=sub.value if sub else None,
            latitude=lat, longitude=lng, price_min=pmin, price_max=pmax, capacity=cap, rating_avg=4.0, rating_count=1,
        )
        r.moods = [PlaceMoodRow(mood_code=m) for m in moods]
        if hours:
            r.hours = [PlaceHourRow(day_of_week=d, open_time=hours[0], close_time=hours[1]) for d in range(7)]
        return r

    session.add_all([
        row(1, Category.CAFE, 200),
        row(2, Category.CAFE, 300, 180, moods=("HIP",)),
        row(3, Category.RESTAURANT, 250, 0),
        row(4, Category.PLAY, 350, 270, sub=SubType.NORAE_BANG),
        row(5, Category.WALK, 150, 45, pmin=0, pmax=0, hours=None),
        row(6, Category.CAFE, 1200, 90),  # 800m 초과: 대중교통
    ])
    session.commit()


@pytest.fixture
def kakao():
    return MockKakaoClient()


@pytest.fixture
def client(kakao):
    settings = Settings(internal_api_key=TEST_KEY, database_url="sqlite://", kakao_client="mock")
    app = create_app(settings=settings, kakao=kakao)

    # lifespan이 장소를 읽기 전에 시드하도록 init을 감싼다
    import app.main as main_mod

    original = main_mod.load_all_places

    def seeded_load(session):
        if not session.query(PlaceRow).count():
            _seed_rows(session)
        return original(session)

    main_mod.load_all_places = seeded_load
    try:
        with TestClient(app) as c:
            c.headers.update({"X-Internal-Api-Key": TEST_KEY})
            yield c
    finally:
        main_mod.load_all_places = original
