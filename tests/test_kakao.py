import pytest

from app.clients.kakao import KakaoError, parse_public_transit


def test_parse_normal_route():
    r = parse_public_transit({"routes": [{"totalTime": 600, "fare": {"total": 1500}, "transfers": 1,
                                          "summary": "버스", "landingURL": "https://map.kakao.com/x",
                                          "sections": [{"path": {"points": [{"x": 127.0, "y": 37.5}]}}]}]})
    assert r.duration_seconds == 600 and r.fare == 1500 and r.path == [[37.5, 127.0]]


@pytest.mark.parametrize("bad", [[], {"routes": []}, {"routes": [{"totalTime": "abc"}]},
                                 {"routes": [{"totalTime": 60, "sections": [{"path": {"points": [{"x": "a", "y": "b"}]}}]}]}])
def test_parse_bad_shapes_raise_kakao_error(bad):
    with pytest.raises(KakaoError):
        parse_public_transit(bad)
