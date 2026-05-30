"""Database setup and SQLAlchemy models."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/store.db")


class Base(DeclarativeBase):
    pass


class EventRecord(Base):
    __tablename__ = "events"

    event_id = Column(String(64), primary_key=True)
    store_id = Column(String(64), index=True, nullable=False)
    camera_id = Column(String(64), nullable=False)
    visitor_id = Column(String(64), index=True, nullable=False)
    event_type = Column(String(32), index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    zone_id = Column(String(64), nullable=True)
    dwell_ms = Column(Integer, default=0, nullable=False)
    is_staff = Column(Boolean, default=False, nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    metadata_json = Column(Text, default="{}", nullable=False)
    ingested_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PosTransactionRecord(Base):
    __tablename__ = "pos_transactions"

    transaction_id = Column(String(64), primary_key=True)
    store_id = Column(String(64), index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), index=True, nullable=False)
    basket_value_inr = Column(Float, nullable=False)


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "connect")
def _sqlite_pragma(dbapi_conn, _connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db() -> None:
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
