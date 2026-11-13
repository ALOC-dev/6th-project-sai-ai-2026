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

## 실제 카카오로 시험하기

평소 서버(8000)는 `.env` 기본값대로 가짜(mock) 카카오를 씁니다. 실제 호출은 시험용 서버를 따로 띄워서만 합니다.

```powershell
# 실제 카카오 서버 (8001): 이 창에서만 KAKAO_CLIENT=real
$env:KAKAO_CLIENT = "real"; .venv/Scripts/uvicorn app.main:app --port 8001
```

테스트 페이지는 `python serve.py --target http://127.0.0.1:8001`로 이 서버에 연결합니다.
실제 서버는 하루 `KAKAO_DAILY_LIMIT`(기본 300)건을 넘기면 카카오를 더 부르지 않습니다.

## 장소 데이터

```bash
python -m scripts.import_places <장소 CSV> --dry-run   # 형식 검사만
python -m scripts.import_places <장소 CSV> --replace   # 기존 장소를 지우고 다시 넣기
```

- 입력 형식: `scripts/places_template.csv`, 안내는 `scripts/places_template_README.md`
- 좌표는 소상공인 상가(상권)정보 API → OpenStreetMap 순으로 찾고, 못 찾으면 CSV의 `latitude`·`longitude`를 씁니다. 카카오 검색 좌표는 저장하지 않습니다.
- 실제 장소 CSV와 DB 파일은 커밋하지 않습니다.

## 환경변수

| 이름 | 설명 |
| --- | --- |
| `INTERNAL_API_KEY` | 백엔드 ↔ AI 내부 인증 키. 비어 있으면 health 외 모든 요청을 거부 |
| `KAKAO_REST_API_KEY` | 카카오 길찾기 REST API 키 |
| `DATABASE_URL` | 개발 `sqlite:///./sai_ai.db`, 운영 `mysql+pymysql://...` |
| `KAKAO_CLIENT` | `mock`(기본, 카카오 호출 안 함) / `real` |
| `KAKAO_DAILY_LIMIT` | real일 때 서버 프로세스당 하루 호출 상한 (기본 300) |
| `SDSC_API_URL`, `SDSC_API_KEY` | 장소 가져오기의 좌표 찾기용 소상공인 상가정보 API |
| `DOCS_ENABLED` | Swagger 공개 여부 (운영 false 권장) |

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
