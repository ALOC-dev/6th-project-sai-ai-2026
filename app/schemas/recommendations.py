from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from app.core.codes import Category, PathSource, ResultStatus, TransportMode
from app.schemas.common import CamelModel, CommonRequest, Id


class RecommendationsRequest(CommonRequest):
    route_count: Literal[1, 3] = Field(description="1(추천 탭) 또는 3(채팅방)")
    main_place_id: Id | None = Field(default=None, description="routeCount=1이면 필수, 3이면 null")

    @model_validator(mode="after")
    def _check_main_place(self):
        if self.route_count == 1 and self.main_place_id is None:
            raise ValueError("routeCount=1이면 mainPlaceId가 필요합니다")
        if self.route_count == 3 and self.main_place_id is not None:
            raise ValueError("routeCount=3이면 mainPlaceId는 null이어야 합니다")
        return self


class StaySegment(CamelModel):
    seq: int
    segment_type: Literal["STAY"] = "STAY"
    place_id: int
    place_name: str
    category_code: Category
    road_address_name: str | None = None
    kakao_place_id: str | None = None
    place_url: str | None = None
    latitude: float
    longitude: float
    arrive_at: datetime
    leave_at: datetime
    price: int = Field(description="1인 예상 비용(원). 뼈대 단계는 장소 priceMin")


class MoveSegment(CamelModel):
    seq: int
    segment_type: Literal["MOVE"] = "MOVE"
    transport_mode: TransportMode
    from_latitude: float
    from_longitude: float
    to_latitude: float
    to_longitude: float
    duration_seconds: int
    distance: int = Field(description="이동 거리(m). ESTIMATE는 직선거리×우회계수")
    fare: int | None = Field(default=None, description="대중교통 요금, 도보면 null")
    transfers: int | None = Field(default=None, description="환승 횟수, 도보면 null")
    route_summary: str | None = Field(default=None, description="대중교통 요약, 아니면 null")
    path_source: PathSource
    path: list[list[float]] = Field(description="[[lat, lng], ...]")
    landing_url: str | None = Field(default=None, description="KAKAO일 때만")


Segment = Annotated[Union[StaySegment, MoveSegment], Field(discriminator="segment_type")]


class Route(CamelModel):
    route_order: int = Field(description="1 = 가장 잘 맞음")
    main_place_count: int = Field(description="1 또는 2")
    title: str = Field(description='규칙 기반 키워드 (예: "조용한 카페 + 산책")')
    reason: str = Field(description='숫자 기반 한 줄 (예: "도보 8분, 예산 안")')
    depart_at: datetime
    return_at: datetime = Field(description="도착지 도착 시각. end가 null이면 마지막 장소를 떠나는 시각")
    buffer_minutes: int = Field(description="복귀 후 여유(분)")
    price_min: int
    price_max: int
    segments: list[Segment] = Field(description="MOVE/STAY 교대, seq 오름차순")


class RecommendationsResponse(CamelModel):
    request_id: int
    status: ResultStatus
    routes: list[Route]
