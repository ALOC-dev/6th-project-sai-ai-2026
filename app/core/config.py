"""환경변수 설정. 키 값은 절대 로그에 남기지 않는다."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    internal_api_key: str = field(repr=False, default="")
    kakao_rest_api_key: str = field(repr=False, default="")
    database_url: str = "sqlite:///./sai_ai.db"
    # mock: 카카오를 부르지 않고 가짜 응답 사용 (뼈대 단계 기본값) / real: 실제 호출
    kakao_client: str = "mock"
    # Swagger(/docs, /openapi.json) 공개 여부. 운영에서는 false 권장
    docs_enabled: bool = True


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        internal_api_key=os.getenv("INTERNAL_API_KEY", ""),
        kakao_rest_api_key=os.getenv("KAKAO_REST_API_KEY", ""),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./sai_ai.db"),
        kakao_client=os.getenv("KAKAO_CLIENT", "mock").lower(),
        docs_enabled=os.getenv("DOCS_ENABLED", "true").lower() in ("1", "true", "yes"),
    )
