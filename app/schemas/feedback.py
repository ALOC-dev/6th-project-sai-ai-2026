from datetime import datetime

from pydantic import Field, model_validator

from app.core.codes import FeedbackType
from app.schemas.common import MAX_USER_IDS, CamelModel, Id, naive_kst


MAX_FEEDBACK_PLACES = 20


class FeedbackRequest(CamelModel):
    user_ids: list[Id] = Field(min_length=1, max_length=MAX_USER_IDS, description="반영할 사용자. 채팅방 루트 선택은 참여자 전원")
    request_id: Id
    type: FeedbackType = Field(description="SELECT / REROLL / RATING")
    place_ids: list[Id] = Field(min_length=1, max_length=MAX_FEEDBACK_PLACES, description="SELECT: 고른 장소(들) / REROLL: 보여준 장소 전부 / RATING: 1개")
    rating: int | None = Field(default=None, ge=1, le=5, description="1~5, RATING일 때만")
    occurred_at: datetime = Field(description="행동 시각 (KST)")

    @model_validator(mode="after")
    def _check(self):
        self.occurred_at = naive_kst(self.occurred_at, "occurredAt")
        if self.type == FeedbackType.RATING:
            if self.rating is None:
                raise ValueError("RATING에는 rating(1~5)이 필요합니다")
            if len(self.place_ids) != 1:
                raise ValueError("RATING은 placeIds가 정확히 1개여야 합니다")
        elif self.rating is not None:
            raise ValueError("rating은 RATING일 때만 보냅니다")
        self.user_ids = list(dict.fromkeys(self.user_ids))
        self.place_ids = list(dict.fromkeys(self.place_ids))
        return self
