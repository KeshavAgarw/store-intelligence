"""Event ingestion with validation, deduplication, and idempotency."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import EventRecord
from app.models import IngestError, IngestRequest, IngestResponse, StoreEvent


def _ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def ingest_events(db: Session, payload: IngestRequest) -> IngestResponse:
    accepted = 0
    rejected = 0
    duplicate = 0
    errors: list[IngestError] = []

    for raw in payload.events:
        try:
            event = StoreEvent.model_validate(raw)
        except Exception as exc:
            rejected += 1
            event_id = raw.get("event_id") if isinstance(raw, dict) else getattr(raw, "event_id", None)
            errors.append(IngestError(event_id=event_id, error=str(exc)))
            continue

        existing = db.get(EventRecord, event.event_id)
        if existing:
            duplicate += 1
            continue

        record = EventRecord(
            event_id=event.event_id,
            store_id=event.store_id,
            camera_id=event.camera_id,
            visitor_id=event.visitor_id,
            event_type=event.event_type.value,
            timestamp=_ensure_utc(event.timestamp),
            zone_id=event.zone_id,
            dwell_ms=event.dwell_ms,
            is_staff=event.is_staff,
            confidence=event.confidence,
            metadata_json=json.dumps(event.metadata.model_dump()),
        )
        db.add(record)
        accepted += 1

    if accepted:
        db.commit()
    else:
        db.rollback()

    return IngestResponse(accepted=accepted, rejected=rejected, duplicate=duplicate, errors=errors)
