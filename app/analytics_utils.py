"""Shared query helpers for store analytics."""

from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import EventRecord, PosTransactionRecord

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
CONVERSION_WINDOW_MINUTES = int(os.getenv("CONVERSION_WINDOW_MINUTES", "5"))
METRICS_REFERENCE_DATE = os.getenv("METRICS_REFERENCE_DATE")


def ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def day_window(reference: datetime | None = None) -> tuple[datetime, datetime]:
    if reference is None and METRICS_REFERENCE_DATE:
        reference = ensure_utc(datetime.fromisoformat(METRICS_REFERENCE_DATE.replace("Z", "+00:00")))
    ref = ensure_utc(reference or datetime.now(timezone.utc))
    start = ref.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def load_pos_transactions(db: Session) -> None:
    path = DATA_DIR / "pos_transactions.csv"
    if not path.exists():
        return
    existing = db.query(PosTransactionRecord).count()
    if existing:
        return
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            db.add(
                PosTransactionRecord(
                    transaction_id=row["transaction_id"],
                    store_id=row["store_id"],
                    timestamp=ensure_utc(datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))),
                    basket_value_inr=float(row["basket_value_inr"]),
                )
            )
    db.commit()


def fetch_store_events(
    db: Session,
    store_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[EventRecord]:
    query = db.query(EventRecord).filter(EventRecord.store_id == store_id)
    if start:
        query = query.filter(EventRecord.timestamp >= start)
    if end:
        query = query.filter(EventRecord.timestamp < end)
    return query.order_by(EventRecord.timestamp).all()


def customer_events(events: list[EventRecord]) -> list[EventRecord]:
    return [event for event in events if not event.is_staff]


def unique_visitors(events: list[EventRecord]) -> set[str]:
    visitors: set[str] = set()
    for event in customer_events(events):
        if event.event_type in {"ENTRY", "REENTRY", "ZONE_ENTER", "ZONE_DWELL", "BILLING_QUEUE_JOIN"}:
            visitors.add(event.visitor_id)
    return visitors


def sessions_from_events(events: list[EventRecord]) -> dict[str, list[EventRecord]]:
    grouped: dict[str, list[EventRecord]] = defaultdict(list)
    for event in customer_events(events):
        grouped[event.visitor_id].append(event)
    for visitor_events in grouped.values():
        visitor_events.sort(key=lambda item: item.timestamp)
    return grouped


def converted_visitors(db: Session, store_id: str, events: list[EventRecord]) -> set[str]:
    converted: set[str] = set()
    pos_rows = (
        db.query(PosTransactionRecord)
        .filter(PosTransactionRecord.store_id == store_id)
        .all()
    )
    billing_events = [
        event
        for event in customer_events(events)
        if event.event_type in {"BILLING_QUEUE_JOIN", "ZONE_ENTER", "ZONE_DWELL"}
        and (event.zone_id == "BILLING" or "BILLING" in (event.zone_id or ""))
    ]
    window = timedelta(minutes=CONVERSION_WINDOW_MINUTES)
    for txn in pos_rows:
        txn_time = ensure_utc(txn.timestamp)
        for event in billing_events:
            event_time = ensure_utc(event.timestamp)
            if event_time <= txn_time <= event_time + window:
                converted.add(event.visitor_id)
    return converted


def parse_metadata(record: EventRecord) -> dict:
    try:
        return json.loads(record.metadata_json or "{}")
    except json.JSONDecodeError:
        return {}
