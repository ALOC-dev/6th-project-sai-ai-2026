"""recommend_places / build_routes 시나리오 (가이드 10절)."""

import asyncio
from datetime import time

from app.clients.kakao import MockKakaoClient
from app.core.codes import Category, Mood, ResultStatus, SubType
from app.schemas.recommendations import RecommendationsRequest, StaySegment
from app.services.build_routes import allocate_stays, build_routes
from app.services.recommend_places import recommend_places
from app.services.travel import TravelService
from app.services.types import PersonalPrefs, PlaceCatalog
from tests.conftest import base_request, make_place


def req(**kw) -> RecommendationsRequest:
    kw.setdefault("routeCount", 3)
    return RecommendationsRequest.model_validate(base_request(**kw))


def run(r: RecommendationsRequest, catalog: PlaceCatalog, kakao=None):
    candidates = recommend_places(r, catalog, PersonalPrefs(), limit=20)
    travel = TravelService(kakao or MockKakaoClient())
    return asyncio.run(build_routes(r, candidates, catalog, travel)), travel


# ---------------------------------------------------------------- recommend_places


def test_hard_filters():
    catalog = PlaceCatalog([
        make_place(1, Category.CAFE, 200),
        make_place(2, Category.CAFE, 2500),  # 거리 초과
        make_place(3, Category.CAFE, 200, price_min=20000, price_max=30000),  # 예산 초과
        make_place(4, Category.CAFE, 200, capacity=1),  # 인원 초과
        make_place(5, Category.CAFE, 200, hours={0: (time(18), time(23))}),  # 월요일 낮 영업 안 함
        make_place(6, Category.CAFE, 200),  # 제외 목록
    ])
    r = req(excludePlaceIds=[6])
    ids = [sp.place.place_id for sp in recommend_places(r, catalog)]
    assert ids == [1]


def test_overnight_hours_are_open():
    p = make_place(1, Category.PLAY, 200, sub_type=SubType.NORAE_BANG, hours={d: (time(12), time(2)) for d in range(7)})
    catalog = PlaceCatalog([p])
    r = req(categories=["PLAY"], freeTimeStartAt="2026-11-16T23:00:00", freeTimeEndAt="2026-11-17T01:30:00")
    assert [sp.place.place_id for sp in recommend_places(r, catalog)] == [1]


def test_short_free_time_gives_no_candidates():
    catalog = PlaceCatalog([make_place(1, Category.CAFE, 200)])
    r = req(freeTimeEndAt="2026-11-16T12:40:00")  # T = 25분 < 카페 최소 40분
    assert recommend_places(r, catalog) == []
    result, _ = run(r, catalog)
    assert result.status == ResultStatus.NO_RESULT and result.routes == []


def test_mood_and_category_raise_score():
    catalog = PlaceCatalog([
        make_place(1, Category.CAFE, 300, moods=frozenset({Mood.HIP})),
        make_place(2, Category.CAFE, 300, moods=frozenset({Mood.CALM})),
        make_place(3, Category.SHOPPING, 300, moods=frozenset({Mood.CALM})),
    ])
    ids = [sp.place.place_id for sp in recommend_places(req(), catalog)]
    assert ids[0] == 2


# ---------------------------------------------------------------- build_routes


def test_route_count_3_uses_distinct_categories():
    catalog = PlaceCatalog([
        make_place(1, Category.CAFE, 200),
        make_place(2, Category.CAFE, 210),
        make_place(3, Category.RESTAURANT, 300, bearing=0),
        make_place(4, Category.WALK, 250, bearing=180, price_min=0, price_max=0),
    ])
    r = req(categories=["CAFE", "RESTAURANT", "WALK"], requestId=1)
    result, _ = run(r, catalog)
    assert result.status == ResultStatus.DONE
    # 루트마다 메인 카테고리가 하나씩 다르다 (2곳 루트라도 원래 메인의 카테고리가 포함됨)
    per_route = [
        {seg.category_code for seg in route.segments if isinstance(seg, StaySegment)} for route in result.routes
    ]
    assert set().union(*per_route) >= {Category.CAFE, Category.RESTAURANT, Category.WALK}
    assert sum(1 for cats in per_route if Category.WALK in cats) >= 1
    assert sum(1 for cats in per_route if Category.RESTAURANT in cats) >= 1


def test_single_category_fills_three_single_place_routes():
    catalog = PlaceCatalog([make_place(i, Category.CAFE, 150 + i * 30, bearing=i * 40) for i in range(1, 6)])
    result, _ = run(req(categories=["CAFE"]), catalog)
    assert result.status == ResultStatus.DONE
    assert len(result.routes) == 3
    assert all(r.main_place_count == 1 for r in result.routes)


def test_partial_when_fewer_places():
    catalog = PlaceCatalog([make_place(1, Category.CAFE, 200)])
    result, _ = run(req(), catalog)
    assert result.status == ResultStatus.PARTIAL and len(result.routes) == 1


def test_route_count_1_two_places_when_time_allows():
    catalog = PlaceCatalog([
        make_place(1, Category.CAFE, 200),
        make_place(2, Category.WALK, 300, price_min=0, price_max=0),
    ])
    r = req(routeCount=1, mainPlaceId=1, categories=["CAFE", "WALK"], freeTimeEndAt="2026-11-16T16:00:00")
    result, _ = run(r, catalog)
    assert result.status == ResultStatus.DONE
    route = result.routes[0]
    assert route.main_place_count == 2
    stays = [s for s in route.segments if isinstance(s, StaySegment)]
    assert stays[0].place_id == 1  # 출발지에 더 가까운 곳 먼저


def test_two_places_margin_boundary():
    """남는시간이 1.3 × (도보 400m + P2 최소)보다 작으면 메인 1곳."""
    catalog = PlaceCatalog([
        make_place(1, Category.CAFE, 100),
        make_place(2, Category.WALK, 150, price_min=0, price_max=0),
    ])
    # T = 180 − 15 − 15 = 150? 아래는 짧은 공강: 2시간 → T=105, 이동 약 4분, 카페 최소 40 → 남는 약 61분
    # 기준: 1.3 × (6.93 + 20) ≈ 35분 → 2곳
    r = req(routeCount=1, mainPlaceId=1, categories=["CAFE", "WALK"], freeTimeEndAt="2026-11-16T14:00:00")
    assert run(r, catalog)[0].routes[0].main_place_count == 2
    # 1시간 15분 → T=60, 남는 약 16분 < 35분 → 1곳
    r = req(routeCount=1, mainPlaceId=1, categories=["CAFE", "WALK"], freeTimeEndAt="2026-11-16T13:15:00")
    assert run(r, catalog)[0].routes[0].main_place_count == 1


def test_heavy_sum_over_limit_stays_single():
    catalog = PlaceCatalog([
        make_place(1, Category.ENTERTAINMENT, 200, sub_type=SubType.ESCAPE_ROOM),  # heavy 4
        make_place(2, Category.CAFE, 250),  # heavy 1 → 합 5 > 4
    ])
    r = req(routeCount=1, mainPlaceId=1, categories=["ENTERTAINMENT", "CAFE"], freeTimeEndAt="2026-11-16T18:00:00")
    assert run(r, catalog)[0].routes[0].main_place_count == 1


def test_no_next_class_ends_at_last_place():
    catalog = PlaceCatalog([make_place(1, Category.CAFE, 200)])
    r = req(routeCount=1, mainPlaceId=1, end=None, freeTimeEndAt="2026-11-16T19:00:00")
    route = run(r, catalog)[0].routes[0]
    assert isinstance(route.segments[-1], StaySegment)
    assert route.return_at == route.segments[-1].leave_at
    assert route.return_at.hour <= 19


def test_far_place_uses_kakao_once_per_pair():
    kakao = MockKakaoClient()
    catalog = PlaceCatalog([make_place(1, Category.CAFE, 1200)])
    r = req(routeCount=1, mainPlaceId=1)
    result, travel = run(r, catalog, kakao)
    assert result.status == ResultStatus.DONE
    assert len(kakao.calls) == 2  # 출발→장소, 장소→도착
    assert result.routes[0].segments[0].path_source.value == "KAKAO"


def test_same_request_id_gives_same_result():
    catalog = PlaceCatalog([make_place(i, c, 150 + i * 40, bearing=i * 50) for i, c in enumerate(
        [Category.CAFE, Category.RESTAURANT, Category.WALK, Category.CAFE, Category.WALK, Category.REST], start=1)])
    r = req(categories=["CAFE", "RESTAURANT", "WALK"], requestId=7)
    a = run(r, catalog)[0].routes
    b = run(r, catalog)[0].routes
    assert [x.model_dump() for x in a] == [x.model_dump() for x in b]


def test_return_within_buffer():
    catalog = PlaceCatalog([make_place(i, Category.STUDY, 100 * i) for i in range(1, 4)])
    r = req(categories=["STUDY"])
    for route in run(r, catalog)[0].routes:
        assert (r.free_time_end_at - route.return_at).total_seconds() >= 15 * 60


def test_allocate_stays_overflow_goes_to_other_place_then_buffer():
    cafe = make_place(1, Category.CAFE, 100)  # 40~120, w2
    rest = make_place(2, Category.REST, 100)  # 20~60, w1
    assert allocate_stays([cafe, rest], 50) is None  # 최소 60 못 채움
    assert allocate_stays([cafe, rest], 90) == [60, 30]
    assert allocate_stays([cafe, rest], 500) == [120, 60]  # 둘 다 최대, 나머지는 여유


def test_category_is_a_filter():
    catalog = PlaceCatalog([make_place(1, Category.CAFE, 200), make_place(2, Category.WALK, 150)])
    assert [sp.place.place_id for sp in recommend_places(req(categories=["CAFE"]), catalog)] == [1]


def test_failed_main_is_replaced_within_same_category():
    """1등 카페가 영업시간 때문에 실패하면, 다른 카테고리가 아니라 다음 카페로 교체한다."""
    from app.services.build_routes import _pick_mains_three

    closes_soon = {d: (time(8), time(12, 45)) for d in range(7)}  # 도착은 되지만 최소 체류 전에 닫음 → 필터에서 걸림
    catalog = PlaceCatalog([
        make_place(1, Category.CAFE, 120, hours=closes_soon),
        make_place(2, Category.CAFE, 400),
        make_place(3, Category.WALK, 150, price_min=0, price_max=0),
        make_place(4, Category.WALK, 160, bearing=200, price_min=0, price_max=0),
    ])
    r = req(categories=["CAFE", "WALK"])
    result, _ = run(r, catalog)
    mains = [route.segments[1].category_code for route in result.routes]
    assert Category.CAFE in mains and Category.WALK in mains


def test_kakao_failure_in_second_place_keeps_single_route():
    class FailAfter(MockKakaoClient):
        async def public_transit(self, *a):
            if len(self.calls) >= 2:
                self.calls.append(a)
                from app.clients.kakao import KakaoError
                raise KakaoError("boom")
            return await super().public_transit(*a)

    catalog = PlaceCatalog([
        make_place(1, Category.CAFE, 1200),
        make_place(2, Category.WALK, 1250, price_min=0, price_max=0),  # P1에서 400m 안, 출발지에서 더 멀다
    ])
    r = req(routeCount=1, mainPlaceId=1, categories=["CAFE", "WALK"], freeTimeEndAt="2026-11-16T17:00:00")
    result, _ = run(r, catalog, FailAfter())
    assert result.status == ResultStatus.DONE
    assert result.routes[0].main_place_count == 1


def test_kakao_failure_for_one_candidate_gives_partial():
    class FailFar(MockKakaoClient):
        async def public_transit(self, from_lat, from_lng, to_lat, to_lng):
            from app.clients.kakao import KakaoError
            raise KakaoError("boom")

    catalog = PlaceCatalog([
        make_place(1, Category.CAFE, 200),
        make_place(2, Category.CAFE, 1200),  # 카카오 필요 → 실패
    ])
    result, _ = run(req(categories=["CAFE"]), catalog, FailFar())
    assert result.status == ResultStatus.PARTIAL and len(result.routes) == 1


def test_kakao_call_budget():
    from app.core.constants import MAX_KAKAO_CALLS_PER_REQUEST

    kakao = MockKakaoClient()
    catalog = PlaceCatalog([make_place(i, Category.CAFE, 1000 + i * 50, bearing=i * 30) for i in range(1, 10)])
    r = req(categories=["CAFE"], end={"name": "도착", "latitude": 37.59, "longitude": 127.05})
    result, travel = run(r, catalog, kakao)
    assert len(kakao.calls) <= MAX_KAKAO_CALLS_PER_REQUEST


def test_play_subtypes_pair_within_limit():
    """PC방(2) + 노래방(2) = 4 ≤ 4 → 메인 2곳."""
    catalog = PlaceCatalog([
        make_place(1, Category.PLAY, 200, sub_type=SubType.PC_BANG),
        make_place(2, Category.PLAY, 250, sub_type=SubType.NORAE_BANG),
    ])
    r = req(routeCount=1, mainPlaceId=1, categories=["PLAY"], freeTimeEndAt="2026-11-16T18:00:00")
    assert run(r, catalog)[0].routes[0].main_place_count == 2


def test_subtypes_belong_to_their_category():
    from app.core.constants import SUBTYPE_CATEGORY, SUBTYPE_RULES

    assert set(SUBTYPE_CATEGORY) == set(SubType) == set(SUBTYPE_RULES)
