from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health", summary="상태 확인 (인증 없음)")
def health(request: Request) -> dict:
    return {"status": "ok", "placeCount": len(request.app.state.catalog)}
