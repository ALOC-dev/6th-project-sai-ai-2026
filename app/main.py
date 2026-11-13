"""사이(SAI) AI 서버. 실행: uvicorn app.main:app --reload"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.api import feedback, health, places, recommendations
from app.api.deps import verify_internal_key
from app.clients.kakao import KakaoClient, MockKakaoClient, RealKakaoClient
from app.core.config import Settings, load_settings
from app.core.errors import register_error_handlers
from app.db.repository import load_all_places
from app.db.session import init_db, make_engine, make_session_factory
from app.services.types import PlaceCatalog

API_PREFIX = "/ai/v1"
logger = logging.getLogger("sai_ai")


def create_app(settings: Settings | None = None, kakao: KakaoClient | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(settings.database_url)
        init_db(engine)
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        with app.state.session_factory() as s:
            app.state.catalog = PlaceCatalog(load_all_places(s))
        if kakao is not None:
            app.state.kakao = kakao
        elif settings.kakao_client == "real":
            app.state.kakao = RealKakaoClient(settings.kakao_rest_api_key, daily_limit=settings.kakao_daily_limit)
        else:
            app.state.kakao = MockKakaoClient()
            logger.warning("KAKAO_CLIENT=mock: 800m 넘는 구간은 가짜 대중교통 값입니다. 운영에서는 KAKAO_CLIENT=real")
        if not settings.internal_api_key:
            logger.warning("INTERNAL_API_KEY가 비어 있어 health 외 모든 요청이 401로 거부됩니다.")
        logger.info("places loaded: %d, kakao client: %s", len(app.state.catalog), type(app.state.kakao).__name__)
        yield
        await app.state.kakao.aclose()
        engine.dispose()

    app = FastAPI(
        title="SAI AI Server",
        version="0.1.0",
        description="공강 시간 장소·루트 추천 AI 서버. 백엔드 전용 내부 API (X-Internal-Api-Key 필요).",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    register_error_handlers(app)

    app.include_router(health.router, prefix=API_PREFIX, tags=["health"])
    protected = [Depends(verify_internal_key)]
    app.include_router(places.router, prefix=API_PREFIX, tags=["places"], dependencies=protected)
    app.include_router(recommendations.router, prefix=API_PREFIX, tags=["recommendations"], dependencies=protected)
    app.include_router(feedback.router, prefix=API_PREFIX, tags=["feedback"], dependencies=protected)
    return app


app = create_app()
