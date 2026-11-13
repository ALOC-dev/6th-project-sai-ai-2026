"""추천 알고리즘 상수 (가이드 7절). 값을 바꿀 때는 이 파일만 고친다."""

from dataclasses import dataclass

from app.core.codes import Category, Mood, SubType

BUFFER_MINUTES = 15  # 확정
CANDIDATE_COUNT = 20  # 잠정
PLACE_LIST_COUNT = 10  # 잠정, FE와 확정 필요
WALK_THRESHOLD_M = 800  # 이하면 도보 추정
WALK_SPEED_M_PER_MIN = 75
WALK_DETOUR_FACTOR = 1.3
SECOND_PLACE_RADIUS_M = 400  # 확정
SECOND_PLACE_MARGIN = 1.3  # 확정
SECOND_PLACE_PROB = 0.5  # routeCount=3에만
MAX_HEAVY_SUM = 4  # 11/14 확정: 공강이 짧아 heavy 4(ENTERTAINMENT 세부 유형)는 어떤 장소와도 묶지 않음
REROLL_LIMIT = 3  # 백엔드가 적용, AI는 참고만

# 하드 필터의 "직선 이동시간" 추정용 (800m 초과 구간). 잠정값, 카카오 실측으로 보정 예정.
TRANSIT_WAIT_MINUTES = 10
TRANSIT_SPEED_M_PER_MIN = 300  # 약 18km/h

# 점수 가중치 w1~w5: 모두 같은 값으로 시작 (가이드 5.1)
SCORE_WEIGHTS = {"mood": 1.0, "category": 1.0, "rating": 1.0, "price": 1.0, "distance": 1.0}
DEFAULT_RATING = 3.0  # 평점이 없는 장소의 중립값

# 개인 선호도 (가이드 5.3)
PREF_SELECT = 3.0
PREF_NOT_SELECTED = -0.5
PREF_REROLL = -0.5
PREF_ALPHA_K = 10  # alpha = n / (n + K)
PREF_SCALE = 3.0  # 개인 점수를 tanh(score / PREF_SCALE)로 -1~1에 맞춤

# 다음 수업 없는 날의 공강 끝 (11/13 잠정). 백엔드가 freeTimeEndAt으로 보내므로 참고용.
NO_CLASS_END_HOUR = 19

# 외부 호출 시간 제한 (백엔드가 최대 10초 기다림)
KAKAO_TIMEOUT_SECONDS = 3.0
MAX_KAKAO_CALLS_PER_REQUEST = 6  # 가이드 6절 최악 기준
REQUEST_TIMEOUT_SECONDS = 9.0


@dataclass(frozen=True)
class StayRule:
    min_minutes: int
    max_minutes: int
    heavy: int
    weight: int = 1


# 카테고리별 값 (초안, PLAY 최소 30분만 확정. heavy는 11/13 원기님 확정)
CATEGORY_RULES: dict[Category, StayRule] = {
    Category.STUDY: StayRule(60, 180, 1, 3),
    Category.CAFE: StayRule(40, 120, 1, 2),
    Category.RESTAURANT: StayRule(40, 70, 1, 1),
    Category.REST: StayRule(20, 60, 3, 1),
    Category.ENTERTAINMENT: StayRule(120, 150, 5, 1),
    Category.WALK: StayRule(20, 60, 1, 1),
    Category.SHOPPING: StayRule(30, 90, 3, 1),
    Category.PLAY: StayRule(30, 120, 3, 2),
}

# 세부 유형 값 (체류는 초안, heavy는 11/14 원기님 확정: PLAY 세부 유형 2, ENTERTAINMENT 세부 유형 4).
# STAY_WEIGHT는 세부 유형에 없으므로 카테고리 값을 쓴다.
SUBTYPE_RULES: dict[SubType, tuple[int, int, int]] = {
    SubType.PC_BANG: (60, 180, 2),
    SubType.NORAE_BANG: (30, 90, 2),
    SubType.BOWLING: (40, 90, 2),
    SubType.BOARD_GAME: (60, 150, 4),
    SubType.ESCAPE_ROOM: (60, 90, 4),
    SubType.EXHIBITION: (40, 90, 4),
    SubType.CINEMA: (120, 150, 4),
}

# 세부 유형이 속하는 카테고리. 장소 적재 시 맞는지 확인한다.
SUBTYPE_CATEGORY: dict[SubType, Category] = {
    SubType.PC_BANG: Category.PLAY,
    SubType.NORAE_BANG: Category.PLAY,
    SubType.BOWLING: Category.PLAY,
    SubType.BOARD_GAME: Category.ENTERTAINMENT,
    SubType.ESCAPE_ROOM: Category.ENTERTAINMENT,
    SubType.EXHIBITION: Category.ENTERTAINMENT,
    SubType.CINEMA: Category.ENTERTAINMENT,
}

# 루트 제목(title) 규칙용 표시 이름
CATEGORY_LABELS: dict[Category, str] = {
    Category.STUDY: "공부",
    Category.CAFE: "카페",
    Category.RESTAURANT: "식사",
    Category.REST: "휴식",
    Category.ENTERTAINMENT: "문화생활",
    Category.WALK: "산책",
    Category.SHOPPING: "쇼핑",
    Category.PLAY: "놀거리",
}

MOOD_LABELS: dict[Mood, str] = {
    Mood.COZY: "아늑한",
    Mood.ROMANTIC: "로맨틱한",
    Mood.HIP: "힙한",
    Mood.ENERGETIC: "활기찬",
    Mood.NOISY: "시끌벅적한",
    Mood.SCARY: "스릴 있는",
    Mood.CALM: "조용한",
}
