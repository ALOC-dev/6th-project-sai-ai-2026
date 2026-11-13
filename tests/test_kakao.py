import pytest

from app.clients.kakao import KakaoError, parse_public_transit

SAMPLE = {
    "status": "OK",
    "properties": {"total": 2, "landingURL": "https://map.kakao.com/link/x"},
    "routes": [
        {
            "properties": {"type": "BUS", "totalDistance": 2300, "totalTime": 960, "transfers": 0, "fare": {"value": 1500}},
            "steps": [
                {"properties": {"type": "WALKING", "distance": 200, "time": 180},
                 "path": {"points": [[127.0587, 37.5838], [127.0590, 37.5840]]}},
                {"properties": {"type": "BUS", "vehicles": [{"name": "273", "type": "BUS"}, {"name": "273", "type": "BUS"}, {"name": "420", "type": "BUS"}]},
                 "path": {"points": [[127.0590, 37.5840], [127.0700, 37.5900]]}},
                {"properties": {"type": "SUBWAY", "vehicles": [{"name": "2호선", "type": "SUBWAY"}]},
                 "path": {"points": [[127.0700, 37.5900], [127.0800, 37.6000]]}},
            ],
        },
        {"properties": {"totalTime": 9999}, "steps": []},
    ],
}


def test_parse_real_shape():
    r = parse_public_transit(SAMPLE)
    assert r.duration_seconds == 960 and r.distance_m == 2300
    assert r.fare == 1500 and r.transfers == 0
    assert r.route_summary == "273 외 1개 → 2호선"
    assert r.landing_url == "https://map.kakao.com/link/x"
    assert r.path[0] == [37.5838, 127.0587]  # [위도, 경도]로 바뀜
    assert len(r.path) == 4  # 구간 경계의 같은 점은 한 번만


@pytest.mark.parametrize("bad", [[], {"routes": []}, {"routes": [{"properties": {"totalTime": "abc"}}]},
                                 {"routes": [{"properties": {"totalTime": 60}, "steps": [{"path": {"points": [["a", "b"]]}}]}]}])
def test_parse_bad_shapes_raise_kakao_error(bad):
    with pytest.raises(KakaoError):
        parse_public_transit(bad)


def test_real_client_sends_x_y_params():
    import asyncio

    import httpx

    from app.clients.kakao import RealKakaoClient

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=SAMPLE)

    client = RealKakaoClient("dummy")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    asyncio.run(client.public_transit(37.5838, 127.0587, 37.6, 127.08))
    assert seen == {"start_x": "127.0587", "start_y": "37.5838", "end_x": "127.08", "end_y": "37.6"}


def test_real_client_daily_limit():
    import asyncio

    import httpx

    from app.clients.kakao import RealKakaoClient

    client = RealKakaoClient("dummy", daily_limit=2)
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=SAMPLE)))

    async def call():
        return await client.public_transit(37.58, 127.05, 37.6, 127.08)

    asyncio.run(call())
    asyncio.run(call())
    with pytest.raises(KakaoError):
        asyncio.run(call())
