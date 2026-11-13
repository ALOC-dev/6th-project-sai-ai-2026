from pydantic import Field

from app.core.codes import Category, Mood, ResultStatus
from app.schemas.common import CamelModel, CommonRequest


class PlacesRequest(CommonRequest):
    """POST /ai/v1/places 요청 = 공통 필드."""


class PlaceItem(CamelModel):
    place_id: int = Field(description="장소 DB ID (recommendations의 mainPlaceId로 다시 옴)")
    place_name: str
    category_code: Category
    moods: list[Mood]
    road_address_name: str | None = None
    kakao_place_id: str | None = None
    place_url: str | None = None
    latitude: float
    longitude: float
    price_min: int = Field(description="1인 최소 비용(원)")
    price_max: int = Field(description="1인 최대 비용(원)")
    distance: int = Field(description="출발지 직선거리(m)")
    rating: float | None = Field(default=None, description="앱 평점 평균, 없으면 null")


class PlacesResponse(CamelModel):
    request_id: int
    status: ResultStatus = Field(description="DONE / NO_RESULT")
    places: list[PlaceItem] = Field(description="점수순 최대 PLACE_LIST_COUNT개")
