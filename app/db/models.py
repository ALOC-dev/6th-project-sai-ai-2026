"""AI 전용 DB `sai_ai` 테이블 (가이드 4절). 백엔드 DB와 달라서 userId·requestId에 외래키를 걸지 않는다."""

from datetime import datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Time,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# SQLite의 자동 증가는 INTEGER PRIMARY KEY에서만 동작하므로, MySQL에서는 BIGINT로 쓴다.
BigId = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):
    pass


class PlaceRow(Base):
    __tablename__ = "places"

    place_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    category_code: Mapped[str] = mapped_column(String(30), index=True)
    sub_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    road_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    price_min: Mapped[int] = mapped_column(Integer, default=0)
    price_max: Mapped[int] = mapped_column(Integer, default=0)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stay_min_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kakao_place_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    place_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    rating_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(10), default="MANUAL")

    moods: Mapped[list["PlaceMoodRow"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    hours: Mapped[list["PlaceHourRow"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class PlaceMoodRow(Base):
    __tablename__ = "place_moods"

    place_id: Mapped[int] = mapped_column(ForeignKey("places.place_id"), primary_key=True)
    mood_code: Mapped[str] = mapped_column(String(30), primary_key=True)


class PlaceHourRow(Base):
    __tablename__ = "place_hours"

    place_id: Mapped[int] = mapped_column(ForeignKey("places.place_id"), primary_key=True)
    day_of_week: Mapped[int] = mapped_column(Integer, primary_key=True)  # 0=월 ... 6=일
    open_time: Mapped[time] = mapped_column(Time)
    close_time: Mapped[time] = mapped_column(Time)  # open보다 이르면 다음 날 새벽까지


class UserPlacePrefRow(Base):
    __tablename__ = "user_place_pref"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    place_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    last_recommended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class RecommendationShownRow(Base):
    __tablename__ = "recommendation_shown"

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(BigInteger, index=True)
    place_id: Mapped[int] = mapped_column(BigInteger)
    route_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_main: Mapped[bool] = mapped_column(Boolean, default=True)


class FeedbackEventRow(Base):
    __tablename__ = "feedback_events"

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    request_id: Mapped[int] = mapped_column(BigInteger, index=True)
    type: Mapped[str] = mapped_column(String(10))
    place_id: Mapped[int] = mapped_column(BigInteger)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime)
