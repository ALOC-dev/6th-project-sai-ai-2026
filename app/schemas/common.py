"""공통 요청 필드 (가이드 8절). JSON은 camelCase, 파이썬 안에서는 snake_case."""

from datetime import datetime, timedelta
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from app.core.codes import Category, Mood


# DB BIGINT 범위 안의 양수 ID
Id = Annotated[int, Field(ge=1, le=2**63 - 1)]

# 입력 상한 (비정상적으로 큰 요청으로 서버가 느려지는 것 방지)
MAX_USER_IDS = 50
MAX_EXCLUDE_IDS = 500
MAX_DISTANCE_M = 50_000
MAX_PRICE = 10_000_000
MAX_HEADCOUNT = 100
MAX_FREE_TIME = timedelta(hours=24)


def naive_kst(dt: datetime, name: str) -> datetime:
    """시간대 표기가 있으면 거부하고, 초 미만은 버린다."""
    if dt.tzinfo is not None:
        raise ValueError(f"{name}은 시간대 표기 없는 KST 문자열이어야 합니다")
    return dt.replace(microsecond=0)


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class Location(CamelModel):
    name: str = Field(description="장소 이름 (예: 미래관)")
    latitude: float = Field(ge=-90, le=90, description="위도")
    longitude: float = Field(ge=-180, le=180, description="경도")


class CommonRequest(CamelModel):
    request_id: Id = Field(description="백엔드 recommendationRequestsId. 로그·난수 시드·피드백 연결용")
    user_ids: list[Id] = Field(min_length=1, max_length=MAX_USER_IDS, description="추천 탭 1명, 채팅방 참여자 전원")
    categories: list[Category] = Field(min_length=1, description="카테고리 코드, 1개 이상 (OR)")
    moods: list[Mood] = Field(min_length=1, description="분위기 코드, 1개 이상 (가산점)")
    headcount: int = Field(ge=1, le=MAX_HEADCOUNT, description="인원 수")
    max_price: int = Field(ge=0, le=MAX_PRICE, description="1인 최대 예산(원)")
    max_distance: int = Field(gt=0, le=MAX_DISTANCE_M, description="출발지 기준 최대 직선거리(m)")
    free_time_start_at: datetime = Field(description="공강 시작 (KST, 시간대 표기 없음)")
    free_time_end_at: datetime = Field(description="공강 끝 = 다음 수업 시작. 다음 수업이 없으면 그날 19:00")
    start: Location = Field(description="출발 위치")
    end: Location | None = Field(default=None, description="도착(다음 수업 건물). 다음 수업이 없으면 null")
    exclude_place_ids: list[Id] = Field(default_factory=list, max_length=MAX_EXCLUDE_IDS, description="제외할 placeId (재추천 시 누적)")

    @model_validator(mode="after")
    def _check_times(self):
        self.free_time_start_at = naive_kst(self.free_time_start_at, "freeTimeStartAt")
        self.free_time_end_at = naive_kst(self.free_time_end_at, "freeTimeEndAt")
        if self.free_time_end_at <= self.free_time_start_at:
            raise ValueError("freeTimeEndAt은 freeTimeStartAt보다 늦어야 합니다")
        if self.free_time_end_at - self.free_time_start_at > MAX_FREE_TIME:
            raise ValueError("공강은 24시간을 넘을 수 없습니다")
        # 중복 코드는 한 번만 본다
        self.categories = list(dict.fromkeys(self.categories))
        self.moods = list(dict.fromkeys(self.moods))
        self.user_ids = list(dict.fromkeys(self.user_ids))
        return self


class ErrorResponse(BaseModel):
    code: str = Field(description="오류 코드 (INVALID_INPUT, UNAUTHORIZED, ...)")
    message: str = Field(description="사람이 읽는 설명")
