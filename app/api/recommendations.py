import asyncio

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app.clients.kakao import KakaoError
from app.core.codes import ErrorCode
from app.core.constants import CANDIDATE_COUNT, REQUEST_TIMEOUT_SECONDS
from app.core.errors import AppError
from app.db import repository
from app.schemas.common import ErrorResponse
from app.schemas.recommendations import RecommendationsRequest, RecommendationsResponse
from app.services.build_routes import PlaceNotFound, build_routes
from app.services.recommend_places import recommend_places
from app.services.travel import TravelService

router = APIRouter()


@router.post(
    "/recommendations",
    response_model=RecommendationsResponse,
    response_model_by_alias=True,
    summary="경로(루트) 추천",
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
async def recommendations(req: RecommendationsRequest, request: Request) -> RecommendationsResponse:
    catalog = request.app.state.catalog
    session_factory = request.app.state.session_factory

    def load_prefs():
        with session_factory() as s:
            return repository.load_personal_prefs(s, req.user_ids)

    def save_shown(shown):
        with session_factory() as s:
            repository.record_shown(s, req.request_id, shown)
            s.commit()

    # DB는 동기 드라이버라 이벤트 루프를 막지 않도록 스레드에서 실행한다
    prefs = await run_in_threadpool(load_prefs)
    candidates = recommend_places(req, catalog, prefs, limit=CANDIDATE_COUNT)
    travel = TravelService(request.app.state.kakao)  # 요청마다 새로 (캐시는 요청 안에서만)
    try:
        result = await asyncio.wait_for(
            build_routes(req, candidates, catalog, travel), timeout=REQUEST_TIMEOUT_SECONDS
        )
    except PlaceNotFound as e:
        raise AppError(404, ErrorCode.PLACE_NOT_FOUND, str(e)) from e
    except KakaoError as e:
        raise AppError(502, ErrorCode.EXTERNAL_API_ERROR, "길찾기 외부 API 호출에 실패했습니다.") from e
    except asyncio.TimeoutError as e:
        raise AppError(504, ErrorCode.TIMEOUT, "처리 시간을 초과했습니다.") from e
    finally:
        await travel.aclose()

    await run_in_threadpool(save_shown, result.shown)
    return RecommendationsResponse(request_id=req.request_id, status=result.status, routes=result.routes)
