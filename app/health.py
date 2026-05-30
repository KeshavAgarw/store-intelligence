"""Health checks and stale feed detection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.analytics_utils import ensure_utc
from app.database import EventRecord, engine
from app.models import HealthResponse, StoreHealth

STALE_THRESHOLD_MINUTES = 10
KNOWN_STORES = ["STORE_BLR_002"]


def check_database() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


def compute_health(db: Session) -> HealthResponse:
    db_ok = check_database()
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(minutes=STALE_THRESHOLD_MINUTES)
    stores: list[StoreHealth] = []
    any_stale = False

    store_ids = (
        db.query(EventRecord.store_id).distinct().all()
        or [(store_id,) for store_id in KNOWN_STORES]
    )

    for (store_id,) in store_ids:
        last_event = (
            db.query(EventRecord.timestamp)
            .filter(EventRecord.store_id == store_id)
            .order_by(EventRecord.timestamp.desc())
            .first()
        )
        last_ts = last_event[0] if last_event else None
        if last_ts is not None:
            last_ts = ensure_utc(last_ts)
        status = "OK"
        if last_ts is None or last_ts < stale_cutoff:
            status = "STALE_FEED"
            any_stale = True
        stores.append(StoreHealth(store_id=store_id, last_event_at=last_ts, status=status))

    overall = "degraded" if (not db_ok or any_stale) else "healthy"
    return HealthResponse(
        status=overall,
        service="store-intelligence-api",
        stores=stores,
        database="connected" if db_ok else "unavailable",
    )
