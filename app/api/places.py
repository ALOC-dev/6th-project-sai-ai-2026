from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.codes import ResultStatus
from app.core.constants import PLACE_LIST_COUNT
from app.db import repository
from app.schemas.common import ErrorResponse
from app.schemas.places import PlaceItem, PlacesRequest, PlacesResponse
from app.services.recommend_places import recommend_places

router = APIRouter()


@router.post(
    "/places",
    response_model=PlacesResponse,
    response_model_by_alias=True,
    summary="장소 추천 (추천 탭 목록)",
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
def places(req: PlacesRequest, request: Request, session: Session = Depends(get_session)) -> PlacesResponse:
    catalog = request.app.state.catalog
    prefs = repository.load_personal_prefs(session, req.user_ids)
    top = recommend_places(req, catalog, prefs, limit=PLACE_LIST_COUNT)
    items = [
        PlaceItem(
            place_id=sp.place.place_id,
            place_name=sp.place.name,
            category_code=sp.place.category,
            moods=sorted(sp.place.moods, key=lambda m: m.value),
            road_address_name=sp.place.road_address,
            kakao_place_id=sp.place.kakao_place_id,
            place_url=sp.place.place_url,
            latitude=sp.place.latitude,
            longitude=sp.place.longitude,
            price_min=sp.place.price_min,
            price_max=sp.place.price_max,
            distance=int(round(sp.distance_m)),
            rating=sp.place.rating_avg,
        )
        for sp in top
    ]
    return PlacesResponse(
        request_id=req.request_id,
        status=ResultStatus.DONE if items else ResultStatus.NO_RESULT,
        places=items,
    )
