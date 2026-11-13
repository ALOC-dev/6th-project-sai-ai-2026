"""모든 고정 코드(enum)는 이 파일 한 곳에만 정의한다 (가이드 4절)."""

from enum import Enum


class Category(str, Enum):
    STUDY = "STUDY"
    CAFE = "CAFE"
    RESTAURANT = "RESTAURANT"
    REST = "REST"
    ENTERTAINMENT = "ENTERTAINMENT"
    WALK = "WALK"
    SHOPPING = "SHOPPING"
    PLAY = "PLAY"


class Mood(str, Enum):
    COZY = "COZY"
    ROMANTIC = "ROMANTIC"
    HIP = "HIP"
    ENERGETIC = "ENERGETIC"
    NOISY = "NOISY"
    SCARY = "SCARY"
    CALM = "CALM"


class SubType(str, Enum):
    # PLAY
    PC_BANG = "PC_BANG"
    NORAE_BANG = "NORAE_BANG"
    BOWLING = "BOWLING"
    # ENTERTAINMENT
    BOARD_GAME = "BOARD_GAME"
    ESCAPE_ROOM = "ESCAPE_ROOM"
    EXHIBITION = "EXHIBITION"
    CINEMA = "CINEMA"


class PlaceSource(str, Enum):
    PUBLIC = "PUBLIC"
    MANUAL = "MANUAL"


class ResultStatus(str, Enum):
    DONE = "DONE"
    PARTIAL = "PARTIAL"
    NO_RESULT = "NO_RESULT"


class SegmentType(str, Enum):
    MOVE = "MOVE"
    STAY = "STAY"


class TransportMode(str, Enum):
    WALK = "WALK"
    PUBLIC_TRANSIT = "PUBLIC_TRANSIT"


class PathSource(str, Enum):
    KAKAO = "KAKAO"
    ESTIMATE = "ESTIMATE"


class FeedbackType(str, Enum):
    SELECT = "SELECT"
    REROLL = "REROLL"
    RATING = "RATING"


class ErrorCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    UNAUTHORIZED = "UNAUTHORIZED"
    PLACE_NOT_FOUND = "PLACE_NOT_FOUND"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    EXTERNAL_API_ERROR = "EXTERNAL_API_ERROR"
    TIMEOUT = "TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"
