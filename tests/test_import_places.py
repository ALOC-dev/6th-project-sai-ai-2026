from datetime import datetime, time

import pytest

from app.core.codes import Category, SubType
from app.services.types import Place
from scripts.import_places import RowError, parse_row

BASE = {
    "name": "테스트카페", "category": "CAFE", "sub_type": "", "road_address": "서울 동대문구 어딘가 1",
    "price_min": "4,500", "price_max": "8000", "moods": "CALM|COZY",
    "mon": "09:00-22:00", "tue": "09:00-22:00", "wed": "09:00-22:00", "thu": "09:00-22:00",
    "fri": "12:00-24:00", "sat": "18:00-02:00", "sun": "휴무",
    "capacity": "4", "stay_min_minutes": "", "kakao_place_id": "123", "memo": "",
}


def row(**kw):
    r = dict(BASE)
    r.update(kw)
    return r


def test_parse_ok():
    p = parse_row(row())
    assert p.price_min == 4500 and p.category == Category.CAFE
    assert 6 not in p.hours  # 일요일 휴무
    assert p.hours[4] == (time(12), time(0))  # 24:00 → 다음 날 0시


def test_hours_semantics_with_place_model():
    p = parse_row(row())
    place = Place(place_id=1, name="x", category=p.category, latitude=0, longitude=0, hours=p.hours)
    assert place.is_open_between(datetime(2026, 11, 20, 23, 0), datetime(2026, 11, 20, 23, 59))  # 금 ~24:00
    assert place.is_open_between(datetime(2026, 11, 22, 1, 0), datetime(2026, 11, 22, 1, 30))  # 토 밤 → 일 새벽
    assert not place.is_open_between(datetime(2026, 11, 22, 12, 0), datetime(2026, 11, 22, 13, 0))  # 일 휴무


def test_always_open_has_no_hours():
    p = parse_row(row(**{d: "상시" for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}))
    assert p.hours == {}


@pytest.mark.parametrize("bad", [
    {"mon": ""},
    {"category": "BAR"},
    {"sub_type": "CINEMA"},  # CAFE에는 세부 유형 없음
    {"moods": ""},
    {"moods": "CALM|COZY|HIP|NOISY"},
    {"price_min": "9000", "price_max": "8000"},
    {"tue": "9시-10시"},
    {**{d: "휴무" for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}},
])
def test_bad_rows(bad):
    with pytest.raises(RowError):
        parse_row(row(**bad))


def test_subtype_category_ok():
    p = parse_row(row(category="PLAY", sub_type="PC_BANG"))
    assert p.sub_type == SubType.PC_BANG
