# SAI AI Server

공강 시간 추천 앱 "사이"의 AI 서버입니다. 백엔드(Spring) 서버만 호출하는 내부 API로, 장소 추천·루트 추천·피드백 수집을 맡습니다.

## 실행

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # 값 채우기 (커밋 금지)
python -m scripts.seed_fake_places   # 가짜 장소 30곳 (개발용)
uvicorn app.main:app --reload
```

- Swagger 문서: http://127.0.0.1:8000/docs
- 상태 확인: `GET /ai/v1/health` (인증 없음)
- 나머지 요청은 `X-Internal-Api-Key` 헤더가 필요합니다. 없거나 틀리면 401.

## 환경변수

| 이름 | 설명 |
| --- | --- |
| `INTERNAL_API_KEY` | 백엔드 ↔ AI 내부 인증 키. 비어 있으면 health 외 모든 요청을 거부 |
| `KAKAO_REST_API_KEY` | 카카오 길찾기 REST API 키 |
| `DATABASE_URL` | 개발 `sqlite:///./sai_ai.db`, 운영 `mysql+pymysql://...` |
| `KAKAO_CLIENT` | `mock`(기본, 카카오 호출 안 함) / `real` |

## API

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/ai/v1/health` | 상태 확인 |
| POST | `/ai/v1/places` | 추천 탭 장소 목록 |
| POST | `/ai/v1/recommendations` | 루트 추천 (routeCount 1 또는 3) |
| POST | `/ai/v1/feedback` | 선택·리롤·별점 피드백 (204) |

오류 본문은 항상 `{"code": "...", "message": "..."}` 입니다.

## 테스트

```bash
python -m pytest -q
```

테스트는 카카오를 실제로 부르지 않습니다(MockKakaoClient).

## 규칙

- 카카오 길찾기 결과는 저장·캐싱하지 않습니다. 같은 요청 안에서만 메모리로 재사용합니다.
- 키·비밀번호는 코드와 커밋에 넣지 않습니다. `.env`는 `.gitignore`에 있습니다.
