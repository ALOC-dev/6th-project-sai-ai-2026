from fastapi.testclient import TestClient

from tests.conftest import base_request


def test_health_needs_no_key(client: TestClient):
    r = client.get("/ai/v1/health", headers={"X-Internal-Api-Key": ""})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_missing_or_wrong_key_is_401(client: TestClient):
    for headers in ({"X-Internal-Api-Key": ""}, {"X-Internal-Api-Key": "wrong"}):
        r = client.post("/ai/v1/places", json=base_request(), headers=headers)
        assert r.status_code == 401
        assert r.json() == {"code": "UNAUTHORIZED", "message": r.json()["message"]}


def test_server_without_key_rejects_everything():
    from app.core.config import Settings
    from app.main import create_app

    app = create_app(settings=Settings(internal_api_key="", database_url="sqlite://"))
    with TestClient(app) as c:
        r = c.post("/ai/v1/places", json=base_request(), headers={"X-Internal-Api-Key": ""})
        assert r.status_code == 401


def test_validation_errors_are_400_invalid_input(client: TestClient):
    bad_bodies = [
        base_request(moods=[]),
        base_request(categories=[]),
        base_request(categories=["UNKNOWN"]),
        base_request(freeTimeEndAt="2026-11-16T11:00:00"),
        base_request(headcount=0),
        {k: v for k, v in base_request().items() if k != "start"},
    ]
    for body in bad_bodies:
        r = client.post("/ai/v1/places", json=body)
        assert r.status_code == 400, body
        assert r.json()["code"] == "INVALID_INPUT"

    for extra in ({"routeCount": 2}, {"routeCount": 1}, {"routeCount": 3, "mainPlaceId": 1}):
        r = client.post("/ai/v1/recommendations", json=base_request(**extra))
        assert r.status_code == 400, extra
        assert r.json()["code"] == "INVALID_INPUT"


def test_unknown_path_uses_error_format(client: TestClient):
    r = client.get("/ai/v1/nope")
    assert r.status_code == 404
    assert set(r.json()) == {"code", "message"}


def test_places_returns_camel_case_sorted_list(client: TestClient):
    r = client.post("/ai/v1/places", json=base_request(categories=["CAFE", "WALK"]))
    assert r.status_code == 200
    body = r.json()
    assert body["requestId"] == 100
    assert body["status"] == "DONE"
    first = body["places"][0]
    for key in ("placeId", "placeName", "categoryCode", "roadAddressName", "kakaoPlaceId", "priceMin", "distance", "rating"):
        assert key in first  # 값이 없어도 필드는 빠지지 않는다


def test_places_exclude_ids(client: TestClient):
    r = client.post("/ai/v1/places", json=base_request(excludePlaceIds=[1, 2, 3, 4, 5, 6]))
    assert r.json() == {"requestId": 100, "status": "NO_RESULT", "places": []}


def test_recommendations_route_count_1_unknown_place_is_404(client: TestClient):
    r = client.post("/ai/v1/recommendations", json=base_request(routeCount=1, mainPlaceId=999))
    assert r.status_code == 404
    assert r.json()["code"] == "PLACE_NOT_FOUND"


def test_recommendations_route_count_3(client: TestClient):
    body = base_request(routeCount=3, categories=["CAFE", "RESTAURANT", "PLAY"])
    r = client.post("/ai/v1/recommendations", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "DONE"
    assert [x["routeOrder"] for x in data["routes"]] == [1, 2, 3]
    seg = data["routes"][0]["segments"]
    assert seg[0]["segmentType"] == "MOVE" and seg[-1]["segmentType"] == "MOVE"
    assert [s["seq"] for s in seg] == list(range(1, len(seg) + 1))
    assert data["routes"][0]["departAt"] == "2026-11-16T12:00:00"


def test_kakao_failure_is_502(client: TestClient, kakao):
    kakao.fail = True
    body = base_request(routeCount=1, mainPlaceId=6)  # 1.2km → 카카오 호출
    r = client.post("/ai/v1/recommendations", json=body)
    assert r.status_code == 502
    assert r.json()["code"] == "EXTERNAL_API_ERROR"


def test_feedback_updates_preference(client: TestClient):
    for rid in range(1, 11):
        fb = {"userIds": [7], "requestId": rid, "type": "SELECT", "placeIds": [2], "occurredAt": "2026-11-16T12:00:00"}
        assert client.post("/ai/v1/feedback", json=fb).status_code == 204
    # 사용자 7은 장소 2(HIP)를 여러 번 골랐으므로 CALM을 원해도 장소 2가 올라와야 한다
    r = client.post("/ai/v1/places", json=base_request(userIds=[7]))
    ids = [p["placeId"] for p in r.json()["places"]]
    r0 = client.post("/ai/v1/places", json=base_request(userIds=[8]))
    ids0 = [p["placeId"] for p in r0.json()["places"]]
    assert ids.index(2) < ids0.index(2)


def test_feedback_validation(client: TestClient):
    bad = [
        {"userIds": [1], "requestId": 1, "type": "RATING", "placeIds": [1], "occurredAt": "2026-11-16T12:00:00"},
        {"userIds": [1], "requestId": 1, "type": "RATING", "placeIds": [1, 2], "rating": 4, "occurredAt": "2026-11-16T12:00:00"},
        {"userIds": [1], "requestId": 1, "type": "SELECT", "placeIds": [1], "rating": 4, "occurredAt": "2026-11-16T12:00:00"},
        {"userIds": [], "requestId": 1, "type": "SELECT", "placeIds": [1], "occurredAt": "2026-11-16T12:00:00"},
    ]
    for body in bad:
        r = client.post("/ai/v1/feedback", json=body)
        assert r.status_code == 400, body


def test_rating_updates_place_rating(client: TestClient):
    fb = {"userIds": [1], "requestId": 1, "type": "RATING", "placeIds": [1], "rating": 1, "occurredAt": "2026-11-16T12:00:00"}
    assert client.post("/ai/v1/feedback", json=fb).status_code == 204
    places = client.post("/ai/v1/places", json=base_request()).json()["places"]
    p1 = next(p for p in places if p["placeId"] == 1)
    assert p1["rating"] == 2.5  # (4.0×1 + 1) / 2


def test_input_limits_are_400(client: TestClient):
    for body in (
        base_request(maxDistance=10**400),
        base_request(requestId=2**70),
        base_request(userIds=list(range(1, 100))),
        base_request(freeTimeStartAt="2026-11-16T12:00:00+09:00"),
    ):
        r = client.post("/ai/v1/places", json=body)
        assert r.status_code == 400, body
    fb = {"userIds": [1], "requestId": 1, "type": "SELECT", "placeIds": [1], "occurredAt": "2026-11-16T12:00:00+09:00"}
    assert client.post("/ai/v1/feedback", json=fb).status_code == 400


def test_microseconds_are_dropped(client: TestClient):
    body = base_request(routeCount=3, freeTimeStartAt="2026-11-16T12:00:00.123456")
    r = client.post("/ai/v1/recommendations", json=body)
    assert r.json()["routes"][0]["departAt"] == "2026-11-16T12:00:00"
