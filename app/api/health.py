from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health", summary="상태 확인 (인증 없음)")
def health(request: Request) -> dict:
    kakao = "real" if type(request.app.state.kakao).__name__ == "RealKakaoClient" else "mock"
    return {"status": "ok", "placeCount": len(request.app.state.catalog), "kakaoClient": kakao}
