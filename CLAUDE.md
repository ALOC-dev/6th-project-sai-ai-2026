# 사이(SAI) AI 서버 작업 가이드

이 레포는 공강 시간 추천 앱 "사이"의 **AI 서버**다. 백엔드(Spring) 서버가 API로 요청을 보내면 AI 서버가 계산해서 API로 결과를 돌려준다. 앱(FE)과 직접 통신하지 않는다.

- 레포: AI `ALOC-dev/6th-project-sai-ai-2026`, BE `ALOC-dev/6th-project-sai-server-2026`, FE `ALOC-dev/6th-project-sai-client-2026`
- 기준 문서: 이 파일 + Notion 허브(261113알록페이지)의 9주차 "경로탐색 알고리즘", "백엔드서버와 api 명세 맞추기", 11/8 회의록.
  - 주의(11/13 확인): 11/6에 고친 원본 Notion 페이지는 삭제됐고, 지금 허브에 있는 사본에는 11/6 수정(routeCount=1의 heavy 규칙, STAY_WEIGHT 배분, 가중치 동일 시작)이 빠져 있다. **Notion과 이 파일이 다르면 이 파일이 최신**이고, Notion을 이 파일에 맞춘다.
- 일정: 12/31까지 주요 기능 + FE/BE 연동. 11/26까지 추천 ERD ↔ AI 명세 정합. PM 보고는 매주 수요일 22:00.
- 이번 주(10주차) AI 과제: 기본 서버 구현, 추천 알고리즘 뼈대 구현.

## 1. 하는 일

| 기능 | 엔드포인트 | 상태 |
| --- | --- | --- |
| 장소 추천 (추천 탭 목록) | `POST /ai/v1/places` | 확정 (11/4, 코드표 11/8) |
| 경로(루트) 추천 | `POST /ai/v1/recommendations` | 확정 (11/4, 코드표 11/8) |
| 사용자 피드백 수집 | `POST /ai/v1/feedback` | 확정 (11/4), 채팅방 선택 반영 방식은 8절 참고 |
| 상태 확인 | `GET /ai/v1/health` | 확정 |
| 시간표 인식(OCR) | 미정 | 백엔드와 명세 합의 전. 12/31 범위 밖으로 두고 지금은 만들지 않는다 |

## 2. 기술 스택과 규칙

- Python 3.11+, **FastAPI**, Pydantic v2, SQLAlchemy 2, httpx(async), numpy, pytest
- JSON 필드명은 **camelCase**. Pydantic 모델에 `alias_generator=to_camel`, `populate_by_name=True`. 파이썬 코드 안에서는 snake_case.
- 응답에서 필드를 빼지 않는다. 값이 없으면 `null`.
- 시각은 시간대 표기 없는 KST ISO-8601 문자열 (`2026-11-03T13:00:00`).
- 오류 본문은 항상 `{"code": "INVALID_INPUT", "message": "..."}` (11/8 BE와 합의).
- 내부 인증: 모든 요청(health 제외)은 `X-Internal-Api-Key` 헤더가 환경변수 `INTERNAL_API_KEY`와 같은지 확인하고, 없거나 다르면 401 `UNAUTHORIZED`. 비교는 `secrets.compare_digest`.
- 백엔드는 동기 HTTP로 부르고 최대 10초 기다린다. 요청 하나를 10초 안에 끝내야 한다.
- 응답은 JSON 한 번에 반환한다. FE 스트리밍 UI는 고도화 단계에서 검토(11/10 결정).
- FastAPI `/docs`(Swagger)가 백엔드용 스키마 문서 역할을 한다. 모델에 description을 꼭 단다.

### 비밀값

- **키·비밀번호를 코드, 커밋, 로그, 이 문서에 절대 쓰지 않는다.** 모두 환경변수로 받고 `.env`는 `.gitignore`에 넣는다. `.env.example`에는 이름만 둔다.

| 환경변수 | 용도 |
| --- | --- |
| `KAKAO_REST_API_KEY` | 카카오맵 길찾기 REST API 키 (발급 완료, 네이티브 앱 키 아님) |
| `INTERNAL_API_KEY` | 백엔드 ↔ AI 내부 인증 키 (양쪽 환경변수에 같은 값) |
| `VWORLD_API_KEY` | 장소 가져오기 스크립트의 주소→좌표 변환 (공공 API) |
| `DATABASE_URL` | AI 전용 DB. 개발 초기 `sqlite:///./sai_ai.db`, 운영은 `mysql+pymysql://<계정>@<호스트>:3306/sai_ai` (백엔드의 jdbc 형식 아님) |

## 3. 카카오 API 제약 (반드시 지킬 것)

- **카카오 결과는 저장·캐싱 금지.** 길찾기 소요시간 임시 캐싱, 로컬(장소 검색) API 결과 저장, 응답 좌표가 들어간 링크 저장 모두 금지 (카카오 데브톡 151653, 151435, 151594).
  - Redis/DB에 카카오 결과를 쌓는 코드를 만들지 않는다. 같은 요청 안에서 메모리로 재사용하는 것만 허용.
  - 장소 데이터는 카카오가 아니라 **자체 장소 DB**(공공데이터 + 팀이 정리한 장소)에서 가져온다.
  - `kakaoPlaceId`와 그 ID로 만든 `placeUrl`은 카카오맵 연결용이라 저장해도 된다 (데브톡 152407).
- 대중교통 길찾기: `GET https://dapi.kakao.com/v2/routing/publictraffic`. 헤더 `Authorization: KakaoAK {KAKAO_REST_API_KEY}`.
  - 경로 ID가 없다. `routes[]` 안에 구간별 `path.points`, `totalTime`, `fare`, `transfers`, `landingURL`이 온다.
- 도보 길찾기: `/v2/routing/walk`, 경유지 최대 5개.
- 카카오 호출은 최소화한다(6절). 타임아웃은 짧게 잡고, 실패하면 502로 돌려준다.

## 4. 자체 장소 DB `sai_ai` (AI 서버 소유)

- 위치: 백엔드 MySQL 안의 별도 데이터베이스 `sai_ai` (11/8 합의, 계정·호스트는 RDS 생성 후 받음). 개발 초기에는 SQLite.
- **장소·피드백 원본은 `sai_ai`가 갖는다 (11/13 원기님 결정).** 백엔드 ERD의 `places`·`userPlaceFeedbacks`는 빼거나 placeId 참조용으로 줄이도록 백엔드에 요청한다. 백엔드는 장소 정보를 AI 응답(STAY 구간·places 응답)으로 받고, 피드백은 `/ai/v1/feedback`으로 보낸다.
- 백엔드 DB(`sai`)와 다른 DB라서 userId·requestId에 외래키를 걸지 않는다.
- 서버 시작 시 장소 전체를 메모리에 올리고 numpy로 거리·필터를 계산한다. 캠퍼스 반경 2km는 수백~수천 건이라 충분히 빠르다.
- 데이터: 공공데이터(소상공인시장진흥공단 상가(상권)정보 등)를 스크립트로 적재 + 분위기 태그·가격·영업시간·체류시간은 팀 스프레드시트에서 import. 뼈대 단계는 가짜 장소 30곳으로 시작.

| 테이블 | 컬럼 |
| --- | --- |
| places | placeId(PK, Long), name, categoryCode, subType(nullable), latitude, longitude, roadAddress, priceMin, priceMax, capacity, stayMinMinutes(nullable, 장소별 덮어쓰기), kakaoPlaceId(nullable), placeUrl(nullable), ratingAvg, ratingCount, source(PUBLIC/MANUAL) |
| place_moods | placeId, moodCode |
| place_hours | placeId, dayOfWeek, openTime, closeTime |
| user_place_pref | userId + placeId(PK), score, lastRecommendedAt, updatedAt (행동이 있었던 장소만) |
| recommendation_shown | requestId, placeId, routeOrder, isMain (보여준 장소 기록, 미선택 감점·리롤용) |
| feedback_events | id, userId, requestId, type, placeId, value, occurredAt (원본 로그) |

### 고정 코드 (11/8 회의 확정)

- 카테고리 `categories` (여러 개 OR 선택): `STUDY`, `CAFE`, `RESTAURANT`, `REST`, `ENTERTAINMENT`(영화관·전시 등), `WALK`, `SHOPPING`, `PLAY`(노래방·PC방 등 가벼운 놀이)
- 분위기 `moods`: `COZY`, `ROMANTIC`, `HIP`, `ENERGETIC`, `NOISY`, `SCARY`, `CALM`. 모두 "이런 곳을 원한다"는 가산점으로만 쓰고, 원하지 않는 분위기를 빼는 기능은 없다.
- 세부 유형 `subType` (사용자는 고르지 않음, AI 내부용, 11/14 원기님 재정리): PLAY → `PC_BANG`, `NORAE_BANG`, `BOWLING` / ENTERTAINMENT → `BOARD_GAME`, `ESCAPE_ROOM`, `EXHIBITION`, `CINEMA`. 세부 유형은 이 두 카테고리에만 있다. 세부 유형이 있으면 체류시간·heavy는 세부 유형 값, 없으면 카테고리 값.
- 코드는 enum 한 곳에만 정의하고 여기저기 문자열로 쓰지 않는다.

## 5. 추천 흐름

| 진입 | 흐름 | 호출 |
| --- | --- | --- |
| 추천 탭(개인) | 조건 입력 → 장소 목록 → 장소 1곳 선택 → 그 장소 중심 루트 1개 | `places` → `recommendations`(routeCount=1, mainPlaceId) |
| 채팅방(친구들) | 조건 입력 → 루트 3개 | `recommendations`(routeCount=3, mainPlaceId=null, userIds=참여자 전원) |

다시 추천(리롤)은 기본 3회까지이고 횟수 제한은 백엔드가 건다. AI는 `excludePlaceIds`로 받은 장소를 빼기만 한다.

### 5.1 recommend_places(req) → 후보 장소 목록

1. **하드 필터**: 모두 만족해야 남는다.
   - 출발지 기준 직선거리 ≤ maxDistance
   - 1인 가격 ≤ maxPrice
   - 공강 동안 영업 중
   - 수용 인원 ≥ headcount
   - 시간 적합: 직선 이동시간(왕복) + 최소 체류시간 ≤ 쓸 수 있는 시간 T
   - excludePlaceIds에 없음
2. **점수**: `w1×분위기 일치 + w2×카테고리 일치 + w3×평점 + w4×가격 여유 − w5×이동거리 + 개인 선호도`. w1~w5는 모두 같은 값으로 시작하고, 데이터가 쌓이면 피팅한다.
3. **반환**: `places` 요청이면 상위 `PLACE_LIST_COUNT`개. 루트 요청이면 상위 `CANDIDATE_COUNT`개를 build_routes에 넘긴다.
4. 순위는 저장하지 않는다. 요청마다 메모리에서 계산한다.

### 5.2 build_routes(req, candidates) → 루트 routeCount개

용어: `T = (공강 끝 − BUFFER_MINUTES) − 공강 시작`

**다음 수업이 없는 날 (11/13 잠정, 다음 모임 전까지)**: 백엔드는 `end = null`, `freeTimeEndAt = 그날 19:00`으로 보낸다. 이때 루트는 마지막 장소에서 끝난다(귀가 MOVE 구간 없음). 돌아갈 수업이 없으므로 BUFFER_MINUTES는 0으로 보고, 아래 식의 `이동(P1 근처→도착)`도 0이다. 마지막 STAY의 leaveAt ≤ 19:00, returnAt = 마지막 leaveAt.

**① 메인 장소 선정**
- routeCount = 1: `mainPlaceId`가 P1으로 확정. DB에 없으면 404 PLACE_NOT_FOUND.
- routeCount = 3: 요청 카테고리(1개 이상) 중 **서로 다른 카테고리**에서 1곳씩, 점수 높은 순으로 3곳. 카테고리가 1~2개뿐이면 루트는 3개를 채우되 모두 메인 1곳.

**② 메인 2곳 판단** (P1 기준)

```
남는시간 = T − 이동(출발→P1) − 최소체류(P1) − 이동(P1 근처→도착)
남는시간 ≥ SECOND_PLACE_MARGIN × (도보시간(400m) + 최소체류(P2))  →  메인 2곳 시도
```

- routeCount = 1: 시간 식과 heavy 규칙을 **둘 다** 통과하면 항상 메인 2곳. 하나라도 걸리면 메인 1곳.
- routeCount = 3: 카테고리가 3개 이상일 때만, 시간 식과 heavy 규칙을 통과한 루트 중 최대 1개를 `SECOND_PLACE_PROB`(50%) 확률로 메인 2곳.
- P2는 후보 중 P1 반경 `SECOND_PLACE_RADIUS_M`(400m) 안에서 고른다. 다른 루트의 카테고리와 상관없이 고른다.
- heavy 규칙: 두 장소의 heavy 합이 `MAX_HEAVY_SUM` 이하일 때만 (7절 표).
- P2를 고른 뒤 실제 이동시간으로 다시 확인하고, 안 맞으면 메인 1곳으로 되돌린다.
- 두 곳 중 출발지에 가까운 곳을 먼저 간다.
- 난수 시드는 `requestId`로 고정한다(재현·디버깅용).

**③ 이동시간 계산**
- 직선 ≤ `WALK_THRESHOLD_M`(800m): `직선거리 × 1.3 ÷ 75m/분` 도보 추정. 카카오 호출 없음. `pathSource = ESTIMATE`, path는 출발·도착 2점.
- 직선 > 800m: 카카오 대중교통 길찾기. `pathSource = KAKAO`, path는 `path.points` 그대로 전달.
- P1→P2는 항상 도보 추정.
- 같은 요청 안에서 같은 출발·도착 쌍은 한 번만 호출(요청 범위 메모리 dict). 독립 호출은 `asyncio.gather`로 동시에.

**④ 체류시간 배분**
- 최소 체류시간을 먼저 배정한다 (장소 stayMinMinutes → 세부 유형 → 카테고리 순으로 찾음).
- 남는 시간은 `STAY_WEIGHT` 비율로 나눈다: `체류(i) = 최소(i) + 남는시간 × w(i) / Σw`. 최대 체류시간을 넘으면 넘친 만큼 다른 장소로, 둘 다 차면 복귀 여유시간으로 돌린다.
- 최소치를 못 채우면 그 루트는 버리고 다음 후보로 교체.

**⑤ 시각 채우기**: MOVE → STAY → (MOVE → STAY) → MOVE 순으로 시각을 붙이고, 도착이 `공강 끝 − 15분` 이내인지 확인. end가 null이면 마지막 MOVE 없이 STAY로 끝나고 마지막 leaveAt ≤ 공강 끝.

**⑥ 결과 status**
- routeCount = 3: 3개 `DONE`, 1~2개 `PARTIAL`, 0개 `NO_RESULT`
- routeCount = 1: 1개 `DONE`, 못 만들면 `NO_RESULT`
- 카카오·서버 오류는 HTTP 5xx (백엔드가 FAILED로 저장)

### 5.3 개인 선호도 학습 (11/8 원기님 초안 + 11/10 결정)

| 행동 | 반영 | 비고 |
| --- | --- | --- |
| 추천 탭에서 장소 선택 (SELECT) | 그 장소 +3 | 루트가 2곳이어도 직접 고른 장소는 반영 |
| 채팅방에서 루트 선택 (SELECT) | 그 루트의 장소 +3, **참여자 전원**에게 | 장소 2곳 이상인 루트는 반영 안 함 |
| 보여줬는데 선택 안 한 루트 | 그 장소 −0.5 | recommendation_shown으로 계산 |
| 다시 추천 (REROLL) | 보여준 장소 −0.5 | |
| 별점 (RATING, 1~5) | (별점 − 3) × 2 | 개인 점수 + 장소 ratingAvg·ratingCount 갱신 |

- 최종 점수 = `(1 − α) × 전체 점수 + α × 개인 점수`, `α = n / (n + 10)` (n = 그 사용자 행동 수)
- 카테고리·분위기 선호는 따로 저장하지 않고, 개인 장소 점수와 장소 태그로 추천할 때마다 계산한다.
- 행동이 있었던 장소만 저장한다(사용자 × 전체 장소 표를 만들지 않음).
- 채팅방(userIds 여러 명)은 참여자 개인 점수의 평균을 쓴다.

## 6. 카카오 호출 최소화 (설계 원칙)

1. 장소 추천은 자체 DB로만 처리 → 0회
2. 후보 목록·좌표를 요청 안에서 재사용, 같은 구간은 1회만
3. 800m 이하 구간은 도보 추정 → 캠퍼스 근처 대부분 0회
4. 시간 안에 못 다녀오는 후보는 호출 전에 제외

요청당 최악: routeCount=3이면 6회, routeCount=1이면 2회. 보통 0~2회.

## 7. 상수 (한 파일에 모아 둔다)

| 상수 | 값 | 비고 |
| --- | --- | --- |
| BUFFER_MINUTES | 15 | 확정 |
| CANDIDATE_COUNT | 20 | 잠정 |
| PLACE_LIST_COUNT | 10 (잠정) | 추천 탭 장소 개수, FE와 확정 필요 |
| WALK_THRESHOLD_M | 800 | 이하면 도보 추정 |
| WALK_SPEED_M_PER_MIN | 75 | 우회계수 1.3 |
| SECOND_PLACE_RADIUS_M | 400 | 확정 |
| SECOND_PLACE_MARGIN | 1.3 | 확정 |
| SECOND_PLACE_PROB | 0.5 | routeCount=3에만 |
| MAX_HEAVY_SUM | 4 (제안) | 원기님 확인 필요 |
| REROLL_LIMIT | 3 | 백엔드가 적용, AI는 참고만 |

카테고리별 값 (초안, PLAY 최소 30분만 확정. heavy 열은 11/13 원기님 확정):

| 카테고리 | 최소(분) | 최대(분) | heavy | STAY_WEIGHT |
| --- | --- | --- | --- | --- |
| STUDY | 60 | 180 | 1 | 3 |
| CAFE | 40 | 120 | 1 | 2 |
| RESTAURANT | 40 | 70 | 1 | 1 |
| REST | 20 | 60 | 3 | 1 |
| ENTERTAINMENT | 120 | 150 | 5 | 1 |
| WALK | 20 | 60 | 1 | 1 |
| SHOPPING | 30 | 90 | 3 | 1 |
| PLAY | 30 | 120 | 3 | 2 |

세부 유형 값 (체류는 초안, heavy는 11/14 확정: PLAY 세부 유형 2, ENTERTAINMENT 세부 유형 4):

| 세부 유형 | 카테고리 | 최소(분) | 최대(분) | heavy |
| --- | --- | --- | --- | --- |
| PC_BANG | PLAY | 60 | 180 | 2 |
| NORAE_BANG | PLAY | 30 | 90 | 2 |
| BOWLING | PLAY | 40 | 90 | 2 |
| BOARD_GAME | ENTERTAINMENT | 60 | 150 | 4 |
| ESCAPE_ROOM | ENTERTAINMENT | 60 | 90 | 4 |
| EXHIBITION | ENTERTAINMENT | 40 | 90 | 4 |
| CINEMA | ENTERTAINMENT | 120 | 150 | 4 |

routeCount는 상수가 아니라 요청값(1 또는 3)이다.

## 8. API 명세

### 공통 요청 필드 (places, recommendations)

`end`만 null 가능(다음 수업 없는 날), 나머지는 모두 필수. maxPrice·maxDistance는 백엔드가 기본값을 채워 보내므로 null이 오지 않는다.

| key | 타입 | 설명 |
| --- | --- | --- |
| requestId | Long | 백엔드 recommendationRequestsId. 로그·시드·피드백 연결 |
| userIds | Long[] | 추천 탭 1명, 채팅방 참여자 전원 (11/8 확정) |
| categories | String[] | 4절 카테고리 코드, 1개 이상 |
| moods | String[] | 4절 분위기 코드, 1개 이상 (빈 배열 불가, 11/13 결정) |
| headcount | Integer | 1 이상 |
| maxPrice | Integer | 1인 최대 예산(원) |
| maxDistance | Integer | 출발지 기준 최대 거리(m) |
| freeTimeStartAt / freeTimeEndAt | String | 공강 시작 / 끝(다음 수업 시작). 끝 > 시작 |
| start / end | Object | `{name, latitude, longitude}` 출발 / 도착(다음 수업 건물). 다음 수업이 없으면 end는 null, freeTimeEndAt은 그날 19:00 |
| excludePlaceIds | Long[] | 첫 요청 `[]`, 재추천 때 이전에 보여준 placeId 누적 |

### POST /ai/v1/places

요청: 공통 필드. 응답:

| key | 타입 | 설명 |
| --- | --- | --- |
| requestId | Long | 그대로 |
| status | String | `DONE` / `NO_RESULT` |
| places[] | Array | 점수순 최대 PLACE_LIST_COUNT개 |
| places[].placeId | Long | 장소 DB ID (recommendations의 mainPlaceId로 다시 옴). 백엔드 ERD에 맞춰 Long (11/13) |
| places[].placeName, categoryCode | String | |
| places[].moods | String[] | |
| places[].roadAddressName | String | null 가능 |
| places[].kakaoPlaceId, placeUrl | String | null 가능 |
| places[].latitude, longitude | Double | |
| places[].priceMin, priceMax | Integer | 1인 비용 범위 |
| places[].distance | Integer | 출발지 직선거리(m) |
| places[].rating | Double | 앱 평점(ratingAvg), null 가능 |

### POST /ai/v1/recommendations

요청: 공통 필드 + `routeCount`(1 또는 3) + `mainPlaceId`(routeCount=1이면 필수, 3이면 null).

응답:

| key | 타입 | 설명 |
| --- | --- | --- |
| requestId | Long | 그대로 |
| status | String | 5.2 ⑥ 참고 |
| routes[] | Array | 0~routeCount개, routeOrder 오름차순 |
| routes[].routeOrder | Integer | 1 = 가장 잘 맞음 |
| routes[].mainPlaceCount | Integer | 1 또는 2 |
| routes[].title / reason | String | 규칙 기반 키워드("조용한 카페 + 산책") / 숫자 기반 템플릿 한 줄("도보 8분, 예산 안"). LLM 쓰지 않음 |
| routes[].departAt / returnAt | String | 출발 / 도착지 도착 시각 |
| routes[].bufferMinutes | Integer | 복귀 후 여유(분) |
| routes[].priceMin / priceMax | Integer | 1인 비용 범위 |
| routes[].segments[] | Array | MOVE/STAY 교대, seq 오름차순 |

STAY: `seq, segmentType="STAY", placeId, placeName, categoryCode, roadAddressName, kakaoPlaceId, placeUrl, latitude, longitude, arriveAt, leaveAt, price`

MOVE: `seq, segmentType="MOVE", transportMode(WALK|PUBLIC_TRANSIT), fromLatitude, fromLongitude, toLatitude, toLongitude, durationSeconds, distance, fare, transfers, routeSummary(대중교통만, 아니면 null), pathSource(KAKAO|ESTIMATE), path([[lat, lng], ...]), landingUrl(KAKAO일 때만)`

- STAY의 이름·주소·좌표는 우리 장소 DB 값이라 백엔드가 저장해도 된다. **백엔드는 routeSegments에 placeId와 함께 placeName·roadAddressName·latitude·longitude를 저장해서, 지난 약속·채팅 화면은 AI를 다시 부르지 않고 그린다 (11/13 결정, 장소 조회 API는 만들지 않음).**
- pathSource=KAKAO 구간의 path·landingUrl·소요시간·요금은 백엔드도 저장하지 않고 앱에 전달만 한다(카카오 약관).

### POST /ai/v1/feedback

| key | 타입 | 설명 |
| --- | --- | --- |
| userIds | Long[] | 반영할 사용자. 추천 탭 1명, 채팅방 루트 선택은 참여자 전원 (11/13 결정) |
| requestId | Long | |
| type | String | `SELECT` / `REROLL` / `RATING` |
| placeIds | Long[] | SELECT: 고른 장소(들) / REROLL: 보여준 장소 전부 / RATING: 1개 |
| rating | Integer | 1~5, RATING일 때만 |
| occurredAt | String | 행동 시각 |

응답 `204 No Content`. 실패해도 백엔드 사용자 흐름은 막지 않는다.

### 오류 코드

| HTTP | code | 의미 |
| --- | --- | --- |
| 200 | (status) | DONE / PARTIAL / NO_RESULT. NO_RESULT면 빈 배열 |
| 400 | INVALID_INPUT | 필수값 누락, categories·moods 빈 배열, 시간 범위 오류, 없는 코드, routeCount가 1·3 아님, routeCount=1인데 mainPlaceId 없음 |
| 401 | UNAUTHORIZED | 내부 API 키 없음/틀림 |
| 404 | PLACE_NOT_FOUND | mainPlaceId가 DB에 없음 |
| 502 | EXTERNAL_API_ERROR | 카카오 오류로 결과를 못 만듦 |
| 504 | TIMEOUT | 처리 시간 초과 |
| 500 | INTERNAL_ERROR | 서버 오류 |

## 8.5 백엔드 ERD(SAI.sql 11/13)와의 차이

ERDCloud는 읽기만 한다. 아래는 백엔드에 전달할 목록이고, AI 코드는 이 파일 명세대로 만든다.

- **places 테이블이 백엔드 DB에 생김**: placeId(Long), sourceId, kakaoPlaceId(Long), placeName, latitude, longitude, category(enum 1개), mood(enum 1개), priceMin/Max(Double), capacity, ratingSum, ratingCount, isOperating. AI 장소 DB(4절)와 겹친다. 장소 원본은 AI `sai_ai`로 결정(11/13)했으므로 빼거나 placeId 참조용으로 줄여 달라고 요청. 영업시간·세부 유형·주소·장소별 분위기 여러 개는 이 테이블에 없다.
- **userPlaceFeedbacks 테이블 신설**: feedbackId, placeId, userId, recommendationRouteId(NOT NULL), feedbackType, score(타입 협의 필요), createdAt. AI의 feedback_events·user_place_pref와 겹친다. recommendationRouteId가 NOT NULL이라 추천 탭 장소 선택·리롤(루트 없음)을 담을 수 없다.
- **routeSegments**: 장소 이름·주소·좌표·placeUrl·categoryGroupCode와 MOVE 좌표를 뺐고 `placeId Long NOT NULL`을 추가. MOVE 구간은 장소가 없어서 NULL 허용이 필요하다. `activity`는 아직 있다(AI는 만들지 않음). 옛 컬럼은 "나중에 써먹을수도?" 테이블로 보관.
- **recommendationRequests**: category·mood가 아직 enum 1개라 여러 개 선택(카테고리 OR)을 못 담는다. excludePlaceIds는 String(JSON 문자열로 쓸 것), chatRoomId는 아직 NOT NULL(추천 탭 요청 불가), mainPlaceId 없음, routeCount는 Long.
- **recommendationRoutes**: segmentsCount, isSelected 추가. isSelected는 SELECT 피드백과 같은 정보라 백엔드가 선택 시 feedback API도 호출해야 한다.
- AI와 무관: timetables.updatedAt, friendRequests.receiverId·activePairKey 추가. 오타(VARCAHAR, Localtime)와 chatMessages·appointment FK NOT NULL은 그대로.

## 9. 디렉터리 구조

11/13 원기님 확정. 새 최상위 폴더는 원기님 확인 후에만 만든다. 기존 `ai-server/`(옛 requirements·가상환경)는 시간표 작업 때 정리한다.

```
app/
  main.py              # FastAPI 앱(create_app), 라우터 등록, 예외 처리기, 시작 시 장소 메모리 적재
  api/                 # health.py, places.py, recommendations.py, feedback.py, deps.py(내부 키 확인·DB 세션)
  schemas/             # common.py, places.py, recommendations.py, feedback.py
  core/                # config.py(환경변수), constants.py(7절 상수), codes.py(enum), errors.py
  db/                  # session.py, models.py, repository.py
  services/            # types.py(메모리 장소 모델), recommend_places.py, build_routes.py, travel.py, preference.py
  clients/kakao.py     # 카카오 호출은 여기 한 곳만 (Real/Mock)
scripts/seed_fake_places.py   # 가짜 장소 30곳
scripts/import_places.py      # 팀 장소 CSV → DB (좌표는 VWorld 공공 지오코더, 카카오 좌표 저장 금지)
scripts/places_template.csv   # 장소 입력 템플릿 (+ places_template_README.md)
tests/                 # conftest.py, test_api.py, test_algorithm.py
.env.example  requirements.txt  pytest.ini  README.md
```

## 10. 작업 규칙

- 카카오 호출은 카카오 클라이언트 모듈 한 곳에만 두고, 테스트에서는 항상 mock한다. 테스트가 실제 카카오를 부르지 않게 한다.
- 알고리즘 함수(recommend_places, build_routes)는 순수 함수에 가깝게 두고 pytest로 시나리오 테스트를 쓴다(공강 짧음, 카테고리 1개, routeCount 1/3, 메인 2곳 경계값, heavy 합 초과).
- 명세(8절)를 바꾸면 Notion "백엔드서버와 api 명세 맞추기"와 이 파일을 같이 고친다.
- 커밋 전에 `.env`, 키 문자열이 diff에 없는지 확인한다.
- 깃허브에 올리기 전에는 진행 과정·알고리즘·판단 이유를 문서로 정리해 원기님 승인을 먼저 받는다.
- 브랜치 이름, 커밋 메시지, PR 제목·본문, 파일 이름·내용에 AI 도구 이름을 넣지 않고, 자동 서명 줄(Co-Authored-By 등)도 넣지 않는다.

## 11. 아직 정해지지 않은 것

- 카테고리·세부 유형별 최소/최대 체류, heavy, STAY_WEIGHT 값과 MAX_HEAVY_SUM (7절 초안, PLAY 30분만 확정)
- PLACE_LIST_COUNT(잠정 10), CANDIDATE_COUNT(잠정 20)
- "보여줬는데 선택 안 한 루트 −0.5"를 언제 적용할지 (다른 루트 SELECT가 올 때 / 일정 시간 뒤)
- 다음 수업 없는 날 규칙(19:00까지, 마지막 장소에서 종료)은 다음 모임 전까지 잠정. 모임에서 확정
- 배포 위치, base URL, `sai_ai` DB 계정 (지윤님 RDS 생성 후)
- 디렉터리 구조
- 백엔드 `places`·`userPlaceFeedbacks`를 빼거나 줄이는 것에 대한 은주님 확인 (AI 원본으로 결정됨, 4절)
- 시간표 인식(OCR) 명세와 일정
- (향후 과제, 11/13 원기님) 장소 분위기(moods) 자동 분류 모델. 카테고리는 공공데이터 업종 코드 매핑 + 이름 키워드 규칙으로 하고, 모델은 분위기 태그에 쓴다. 리뷰 등 텍스트 출처의 이용 조건과 팀 라벨 데이터 확보가 먼저.
