"""가짜 장소 30곳 시드 (뼈대 단계용).

실행: python -m scripts.seed_fake_places [--reset]
- DATABASE_URL(.env)의 DB에 테이블을 만들고 가짜 장소를 넣는다.
- 캠퍼스 기준점 주변 반경 약 1.5km에 고정 난수(seed=42)로 배치한다. 실제 상호가 아니다.
"""

from __future__ import annotations

import argparse
import math
import random
from datetime import time

from sqlalchemy import delete, func, select

from app.core.codes import Category, Mood, PlaceSource, SubType
from app.core.config import load_settings
from app.db.models import PlaceHourRow, PlaceMoodRow, PlaceRow
from app.db.session import init_db, make_engine, make_session_factory

# 캠퍼스 기준점 (대략적인 위치, 테스트용)
CAMPUS_LAT = 37.5838
CAMPUS_LNG = 127.0587

# (카테고리, 세부 유형, 개수, 가격 범위, 영업시간)
PLAN: list[tuple[Category, SubType | None, int, tuple[int, int], tuple[time, time] | None]] = [
    (Category.CAFE, None, 6, (4000, 8000), (time(8), time(22))),
    (Category.STUDY, None, 3, (2000, 6000), (time(9), time(23))),
    (Category.RESTAURANT, None, 6, (7000, 13000), (time(11), time(21))),
    (Category.REST, None, 2, (0, 3000), (time(7), time(22))),
    (Category.WALK, None, 3, (0, 0), None),
    (Category.SHOPPING, None, 2, (5000, 30000), (time(10), time(21))),
    (Category.PLAY, SubType.NORAE_BANG, 2, (3000, 8000), (time(12), time(2))),
    (Category.PLAY, SubType.PC_BANG, 1, (2000, 6000), (time(0), time(23, 59))),
    (Category.ENTERTAINMENT, SubType.BOARD_GAME, 1, (5000, 9000), (time(12), time(23))),
    (Category.PLAY, SubType.BOWLING, 1, (6000, 12000), (time(11), time(23))),
    (Category.ENTERTAINMENT, SubType.CINEMA, 2, (12000, 15000), (time(9), time(23, 59))),
    (Category.ENTERTAINMENT, SubType.EXHIBITION, 1, (0, 10000), (time(10), time(18))),
]

NAME = {
    Category.CAFE: "카페",
    Category.STUDY: "스터디카페",
    Category.RESTAURANT: "식당",
    Category.REST: "쉼터",
    Category.WALK: "산책로",
    Category.SHOPPING: "상점",
    SubType.NORAE_BANG: "코인노래방",
    SubType.PC_BANG: "PC방",
    SubType.BOARD_GAME: "보드게임카페",
    SubType.ESCAPE_ROOM: "방탈출카페",
    SubType.BOWLING: "볼링장",
    SubType.CINEMA: "영화관",
    SubType.EXHIBITION: "전시관",
}


def offset(lat: float, lng: float, dist_m: float, bearing_deg: float) -> tuple[float, float]:
    b = math.radians(bearing_deg)
    dlat = dist_m * math.cos(b) / 111_320
    dlng = dist_m * math.sin(b) / (111_320 * math.cos(math.radians(lat)))
    return round(lat + dlat, 6), round(lng + dlng, 6)


def build_rows() -> list[PlaceRow]:
    rng = random.Random(42)
    moods = list(Mood)
    rows: list[PlaceRow] = []
    seq = 0
    for category, sub_type, count, (pmin, pmax), hours in PLAN:
        for i in range(count):
            seq += 1
            # 대부분 800m 안(도보), 일부는 800m~1.5km(대중교통)
            dist = rng.uniform(80, 750) if rng.random() < 0.75 else rng.uniform(850, 1500)
            lat, lng = offset(CAMPUS_LAT, CAMPUS_LNG, dist, rng.uniform(0, 360))
            label = NAME[sub_type] if sub_type else NAME[category]
            row = PlaceRow(
                name=f"가짜{label} {i + 1}호점",
                category_code=category.value,
                sub_type=sub_type.value if sub_type else None,
                latitude=lat,
                longitude=lng,
                road_address=f"서울시 동대문구 가짜로 {seq}",
                price_min=pmin,
                price_max=pmax,
                capacity=rng.choice([4, 8, 20, 50]),
                rating_avg=round(rng.uniform(3.0, 4.8), 1),
                rating_count=rng.randint(1, 30),
                source=PlaceSource.MANUAL.value,
            )
            row.moods = [PlaceMoodRow(mood_code=m.value) for m in rng.sample(moods, k=rng.randint(1, 3))]
            if hours is not None:
                row.hours = [PlaceHourRow(day_of_week=d, open_time=hours[0], close_time=hours[1]) for d in range(7)]
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="기존 장소를 지우고 다시 넣는다")
    args = parser.parse_args()

    settings = load_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    with make_session_factory(engine)() as session:
        existing = session.scalar(select(func.count()).select_from(PlaceRow)) or 0
        if existing and not args.reset:
            print(f"이미 장소 {existing}곳이 있습니다. 다시 넣으려면 --reset")
            return
        if args.reset:
            session.execute(delete(PlaceHourRow))
            session.execute(delete(PlaceMoodRow))
            session.execute(delete(PlaceRow))
        rows = build_rows()
        session.add_all(rows)
        session.commit()
        print(f"가짜 장소 {len(rows)}곳을 넣었습니다.")


if __name__ == "__main__":
    main()
