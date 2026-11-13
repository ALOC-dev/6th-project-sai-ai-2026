"""팀이 정리한 장소 CSV를 장소 DB에 넣는다.

실행 예:
    python -m scripts.import_places C:\\dev\\data\\places_filled.csv --dry-run
    python -m scripts.import_places C:\\dev\\data\\places_filled.csv --replace

- 형식은 scripts/places_template_README.md 참고.
- 좌표: CSV에 latitude, longitude 열이 있으면 그 값을 쓰고, 없으면 주소를 좌표로 바꾼다.
  기본은 OpenStreetMap Nominatim(키 불필요, ODbL 라이선스라 저장 가능, 1초에 1건 제한).
  건물 번호까지 일치한 결과만 쓰고, 도로 전체만 잡히면 그 장소는 빼고 좌표를 직접 넣으라고 알려 준다.
  VWORLD_API_KEY가 있으면 --geocoder vworld로 VWorld를 쓸 수 있다. 카카오 검색 결과 좌표는 저장하지 않는다.
- --geocoder sdsc (기본): 소상공인 상가(상권)정보 API(SDSC_API_URL, SDSC_API_KEY)로 캠퍼스 반경 상가를
  한 번 받아 도로명주소(도로명 + 건물번호)가 같은 상가의 좌표를 쓴다. 못 찾은 곳만 OSM으로 한 번 더 시도한다.
- 영업시간이 비어 있는 장소는 넣지 않는다 (비어 있으면 서버가 '항상 열림'으로 보기 때문).
- --replace: 기존 장소(places, place_moods, place_hours)를 모두 지우고 새로 넣는다.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from sqlalchemy import delete

from app.core.codes import Category, Mood, PlaceSource, SubType
from app.core.config import load_settings
from app.core.constants import SUBTYPE_CATEGORY
from app.db.models import PlaceHourRow, PlaceMoodRow, PlaceRow
from app.db.session import init_db, make_engine, make_session_factory

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]  # dayOfWeek 0~6
HOURS_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$")
VWORLD_URL = "https://api.vworld.kr/req/address"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# "서울 동대문구 망우로 30-1 1층" → "서울 동대문구 망우로 30-1" (층·호수·건물명 제거)
ADDRESS_CORE_RE = re.compile(r"^(.*?(?:로|길)\s*\d+(?:-\d+)?(?=\s|$)|.*?[동리가]\s*(?:산\s*)?\d+(?:-\d+)?(?=\s|$))")


class RowError(ValueError):
    pass


@dataclass
class ParsedPlace:
    name: str
    category: Category
    sub_type: SubType | None
    road_address: str
    price_min: int
    price_max: int
    moods: list[Mood]
    hours: dict[int, tuple[time, time]] = field(default_factory=dict)  # 비어 있으면 상시
    capacity: int | None = None
    stay_min_minutes: int | None = None
    kakao_place_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None


def _int_or_none(v: str, col: str) -> int | None:
    v = (v or "").strip().replace(",", "")
    if not v:
        return None
    if not v.isdigit():
        raise RowError(f"{col}: 숫자가 아님 ({v})")
    return int(v)


def _to_time(h: str, m: str) -> time:
    hh, mm = int(h), int(m)
    if hh == 24 and mm == 0:
        return time(0, 0)  # 24:00 = 다음 날 0시 (닫는 시각이 여는 시각보다 이르면 다음 날로 처리됨)
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise RowError(f"시각 범위 오류 ({h}:{m})")
    return time(hh, mm)


def parse_hours(row: dict) -> dict[int, tuple[time, time]]:
    values = [(row.get(d) or "").strip() for d in DAYS]
    if any(v == "" for v in values):
        missing = [d for d, v in zip(DAYS, values) if v == ""]
        raise RowError(f"영업시간 비어 있음: {', '.join(missing)}")
    if all(v == "상시" for v in values):
        return {}
    if all(v == "휴무" for v in values):
        raise RowError("모든 요일이 휴무")
    hours: dict[int, tuple[time, time]] = {}
    for idx, v in enumerate(values):
        if v == "휴무":
            continue
        if v == "상시":
            hours[idx] = (time(0, 0), time(0, 0))  # 0시~다음 날 0시 = 24시간
            continue
        m = HOURS_RE.match(v)
        if not m:
            raise RowError(f"{DAYS[idx]} 영업시간 형식 오류 ({v})")
        hours[idx] = (_to_time(m[1], m[2]), _to_time(m[3], m[4]))
    return hours


def parse_row(row: dict) -> ParsedPlace:
    name = (row.get("name") or "").strip()
    if not name:
        raise RowError("name 비어 있음")
    try:
        category = Category((row.get("category") or "").strip())
    except ValueError as e:
        raise RowError(f"category 코드 오류 ({row.get('category')})") from e
    sub_raw = (row.get("sub_type") or "").strip()
    sub_type = None
    if sub_raw:
        try:
            sub_type = SubType(sub_raw)
        except ValueError as e:
            raise RowError(f"sub_type 코드 오류 ({sub_raw})") from e
        if SUBTYPE_CATEGORY[sub_type] != category:
            raise RowError(f"sub_type {sub_raw}는 {SUBTYPE_CATEGORY[sub_type].value} 카테고리용")
    address = (row.get("road_address") or "").strip()
    if not address:
        raise RowError("road_address 비어 있음")
    pmin = _int_or_none(row.get("price_min", ""), "price_min")
    pmax = _int_or_none(row.get("price_max", ""), "price_max")
    if pmin is None and pmax is None:
        raise RowError("price_min·price_max 둘 다 비어 있음")
    pmin = pmin if pmin is not None else pmax
    pmax = pmax if pmax is not None else pmin
    if pmin > pmax:  # type: ignore[operator]
        raise RowError(f"price_min({pmin}) > price_max({pmax})")
    moods_raw = [m.strip() for m in (row.get("moods") or "").split("|") if m.strip()]
    if not 1 <= len(moods_raw) <= 3:
        raise RowError("moods는 1~3개")
    try:
        moods = [Mood(m) for m in moods_raw]
    except ValueError as e:
        raise RowError(f"moods 코드 오류 ({row.get('moods')})") from e
    lat = (row.get("latitude") or "").strip()
    lng = (row.get("longitude") or "").strip()
    kakao_id = (row.get("kakao_place_id") or "").strip() or None
    if kakao_id and not kakao_id.isdigit():
        raise RowError(f"kakao_place_id는 숫자만 ({kakao_id})")
    return ParsedPlace(
        name=name,
        category=category,
        sub_type=sub_type,
        road_address=address,
        price_min=pmin,  # type: ignore[arg-type]
        price_max=pmax,  # type: ignore[arg-type]
        moods=moods,
        hours=parse_hours(row),
        capacity=_int_or_none(row.get("capacity", ""), "capacity"),
        stay_min_minutes=_int_or_none(row.get("stay_min_minutes", ""), "stay_min_minutes"),
        kakao_place_id=kakao_id,
        latitude=float(lat) if lat else None,
        longitude=float(lng) if lng else None,
    )


def geocode_vworld(client: httpx.Client, key: str, address: str) -> tuple[float, float]:
    """도로명주소 → (위도, 경도). 지번 주소면 parcel로 한 번 더 시도한다."""
    for addr_type in ("road", "parcel"):
        resp = client.get(
            VWORLD_URL,
            params={
                "service": "address",
                "request": "getcoord",
                "crs": "epsg:4326",
                "format": "json",
                "type": addr_type,
                "address": address,
                "key": key,
            },
        )
        resp.raise_for_status()
        data = resp.json().get("response", {})
        if data.get("status") == "OK":
            point = data["result"]["point"]
            return float(point["y"]), float(point["x"])
    raise RowError(f"주소를 좌표로 바꾸지 못함 ({address})")


def address_core(address: str) -> str:
    m = ADDRESS_CORE_RE.match(address.strip())
    return m.group(1) if m else address.strip()


def geocode_nominatim(client: httpx.Client, address: str) -> tuple[float, float]:
    """OpenStreetMap Nominatim. 건물 번호(house_number)까지 맞은 결과만 받는다."""
    import time as _time

    _time.sleep(1.1)  # 이용 정책: 1초에 1건
    resp = client.get(
        NOMINATIM_URL,
        params={"q": address_core(address), "format": "jsonv2", "limit": 1, "countrycodes": "kr", "addressdetails": 1},
    )
    resp.raise_for_status()
    results = resp.json()
    if not results or "house_number" not in results[0].get("address", {}):
        raise RowError(f"건물 단위로 찾지 못함 ({address}). CSV에 latitude, longitude를 직접 넣어 주세요")
    return float(results[0]["lat"]), float(results[0]["lon"])


CAMPUS_CENTER = (37.5838, 127.0587)  # (위도, 경도) 상가 목록을 받을 중심점


def normalize_road(addr: str) -> str:
    """'서울특별시 동대문구 망우로 30-1 1층' / '서울 동대문구 망우로 30-1' → '망우로30-1'"""
    core = address_core(addr)
    m = re.search(r"([가-힣0-9]+(?:로|길))\s*(\d+(?:-\d+)?)$", core)
    return f"{m.group(1)}{m.group(2)}" if m else core.replace(" ", "")


def load_sdsc_index(client: httpx.Client, base_url: str, key: str, radius_m: int = 2000) -> dict[str, tuple[float, float]]:
    """캠퍼스 반경 상가 전체를 받아 '도로명+건물번호' → 좌표 사전을 만든다 (공공데이터, 저장 가능)."""
    index: dict[str, tuple[float, float]] = {}
    page = 1
    while True:
        resp = client.get(
            f"{base_url}/storeListInRadius",
            params={"serviceKey": key, "pageNo": page, "numOfRows": 1000, "radius": radius_m,
                    "cx": CAMPUS_CENTER[1], "cy": CAMPUS_CENTER[0], "type": "json"},
        )
        resp.raise_for_status()
        body = resp.json().get("body", {})
        items = body.get("items") or []
        for it in items:
            addr = it.get("rdnmAdr") or ""
            if addr and it.get("lat") and it.get("lon"):
                index.setdefault(normalize_road(addr), (float(it["lat"]), float(it["lon"])))
        if not items or page * 1000 >= int(body.get("totalCount") or 0):
            break
        page += 1
    return index


def place_url(kakao_id: str | None) -> str | None:
    return f"https://place.map.kakao.com/{kakao_id}" if kakao_id else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # 윈도우 콘솔(cp949)에서 é 같은 문자 오류 방지
    parser = argparse.ArgumentParser(description="장소 CSV를 장소 DB에 넣는다")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="검사만 하고 DB에 쓰지 않는다")
    parser.add_argument("--replace", action="store_true", help="기존 장소를 모두 지우고 넣는다")
    parser.add_argument("--geocoder", choices=["sdsc", "osm", "vworld"], default="sdsc", help="주소→좌표 변환기 (기본 sdsc)")
    args = parser.parse_args()

    with args.csv_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    parsed: list[ParsedPlace] = []
    errors: list[str] = []
    for i, row in enumerate(rows, start=2):  # 1행은 머리글
        try:
            parsed.append(parse_row(row))
        except RowError as e:
            errors.append(f"{i}행 {row.get('name', '')}: {e}")

    print(f"CSV {len(rows)}행 중 통과 {len(parsed)}곳, 제외 {len(errors)}곳")
    for e in errors:
        print("  - " + e)

    need_geo = [p for p in parsed if p.latitude is None or p.longitude is None]
    if need_geo:
        load_dotenv()
        key = os.getenv("VWORLD_API_KEY", "")
        if args.geocoder == "vworld" and not key:
            print("--geocoder vworld에는 .env의 VWORLD_API_KEY가 필요합니다.")
            return 1
        sdsc_index: dict[str, tuple[float, float]] = {}
        print(f"좌표 변환 {len(need_geo)}곳 ({args.geocoder})...")
        headers = {"User-Agent": "sai-place-import/0.1"}
        with httpx.Client(timeout=30.0, headers=headers) as client:
            if args.geocoder == "sdsc":
                sdsc_url, sdsc_key = os.getenv("SDSC_API_URL", ""), os.getenv("SDSC_API_KEY", "")
                if not (sdsc_url and sdsc_key):
                    print("--geocoder sdsc에는 .env의 SDSC_API_URL, SDSC_API_KEY가 필요합니다.")
                    return 1
                sdsc_index = load_sdsc_index(client, sdsc_url, sdsc_key)
                print(f"  상가 주소 {len(sdsc_index)}건을 받았습니다.")
            for p in list(need_geo):
                try:
                    hit = sdsc_index.get(normalize_road(p.road_address))
                    if hit:
                        p.latitude, p.longitude = hit
                        print(f"  ok(상가) {p.name}: {p.latitude:.6f}, {p.longitude:.6f}")
                        continue
                    if args.geocoder == "vworld":
                        p.latitude, p.longitude = geocode_vworld(client, key, p.road_address)
                    else:
                        p.latitude, p.longitude = geocode_nominatim(client, p.road_address)
                    print(f"  ok(지도) {p.name}: {p.latitude:.6f}, {p.longitude:.6f}")
                except (RowError, httpx.HTTPError) as e:
                    print(f"  - {p.name}: {e}")
                    parsed.remove(p)
        print(f"최종 {len(parsed)}곳")

    if args.dry_run:
        print("--dry-run: DB에 쓰지 않았습니다.")
        return 0

    settings = load_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    with make_session_factory(engine)() as session:
        if args.replace:
            session.execute(delete(PlaceHourRow))
            session.execute(delete(PlaceMoodRow))
            session.execute(delete(PlaceRow))
        for p in parsed:
            row = PlaceRow(
                name=p.name,
                category_code=p.category.value,
                sub_type=p.sub_type.value if p.sub_type else None,
                latitude=p.latitude,
                longitude=p.longitude,
                road_address=p.road_address,
                price_min=p.price_min,
                price_max=p.price_max,
                capacity=p.capacity,
                stay_min_minutes=p.stay_min_minutes,
                kakao_place_id=p.kakao_place_id,
                place_url=place_url(p.kakao_place_id),
                rating_avg=None,
                rating_count=0,
                source=PlaceSource.MANUAL.value,
            )
            row.moods = [PlaceMoodRow(mood_code=m.value) for m in p.moods]
            row.hours = [PlaceHourRow(day_of_week=d, open_time=o, close_time=c) for d, (o, c) in p.hours.items()]
            session.add(row)
        session.commit()
    print(f"장소 {len(parsed)}곳을 넣었습니다." + (" (기존 장소는 모두 지움)" if args.replace else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
