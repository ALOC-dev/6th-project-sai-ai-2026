# 실제 장소 입력 템플릿 (places_template.csv)

한 줄에 장소 하나. 예시 3줄은 지우고 채워 주세요. 엑셀에서 열고 저장할 때는 "CSV UTF-8"로 저장합니다.

| 열 | 필수 | 형식 |
| --- | --- | --- |
| name | 필수 | 장소 이름 |
| category | 필수 | STUDY, CAFE, RESTAURANT, REST, ENTERTAINMENT, WALK, SHOPPING, PLAY 중 1개 |
| sub_type | 선택 | PC_BANG, NORAE_BANG, BOWLING (PLAY) / BOARD_GAME, ESCAPE_ROOM, EXHIBITION, CINEMA (ENTERTAINMENT). 해당 없으면 비움 |
| road_address | 필수 | 도로명주소. 좌표는 이 주소로 공공 주소 API에서 변환 |
| price_min, price_max | 필수 | 1인 비용(원), 숫자만. 무료면 0 |
| moods | 필수 | COZY, ROMANTIC, HIP, ENERGETIC, NOISY, SCARY, CALM 중 1~3개를 `\|`로 연결 (예: `CALM\|COZY`) |
| mon ~ sun | 필수 | `09:00-22:00` / 자정 넘김 `18:00-02:00` / `휴무` / `상시` |
| capacity | 선택 | 대략 수용 인원, 숫자 |
| stay_min_minutes | 선택 | 이 장소만 최소 체류시간을 다르게 할 때(분) |
| kakao_place_id | 선택 | 카카오맵 장소 링크 `place.map.kakao.com/12345678`의 숫자 |
| memo | 선택 | 메모 (DB에 넣지 않음) |

평점·좌표 열은 없습니다. 평점은 앱 별점으로 쌓이고, 카카오 검색으로 얻은 좌표는 저장할 수 없기 때문입니다.
