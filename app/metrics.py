"""Real-time store metrics computation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.analytics_utils import (
    converted_visitors,
    customer_events,
    day_window,
    fetch_store_events,
    load_pos_transactions,
    parse_metadata,
    unique_visitors,
)
from app.database import PosTransactionRecord
from app.models import StoreMetrics, ZoneMetric


def compute_metrics(db: Session, store_id: str) -> StoreMetrics:
    load_pos_transactions(db)
    start, end = day_window()
    events = fetch_store_events(db, store_id, start, end)
    visitors = unique_visitors(events)
    converted = converted_visitors(db, store_id, events)

    unique_count = len(visitors)
    conversion_rate = (len(converted) / unique_count) if unique_count else 0.0

    dwell_by_zone: dict[str, list[int]] = defaultdict(list)
    visit_counts: dict[str, int] = defaultdict(int)
    for event in customer_events(events):
        if event.zone_id and event.event_type in {"ZONE_DWELL", "ZONE_ENTER"}:
            visit_counts[event.zone_id] += 1 if event.event_type == "ZONE_ENTER" else 0
            if event.event_type == "ZONE_DWELL" and event.dwell_ms:
                dwell_by_zone[event.zone_id].append(event.dwell_ms)

    zone_metrics = [
        ZoneMetric(
            zone_id=zone_id,
            avg_dwell_ms=(sum(values) / len(values)) if values else 0.0,
            visit_count=visit_counts.get(zone_id, len(values)),
        )
        for zone_id, values in sorted(dwell_by_zone.items())
    ]

    queue_depth = 0
    for event in reversed(customer_events(events)):
        if event.event_type in {"BILLING_QUEUE_JOIN", "ZONE_ENTER"} and event.zone_id == "BILLING":
            meta = parse_metadata(event)
            queue_depth = meta.get("queue_depth") or 0
            break

    joins = sum(1 for event in customer_events(events) if event.event_type == "BILLING_QUEUE_JOIN")
    abandons = sum(1 for event in customer_events(events) if event.event_type == "BILLING_QUEUE_ABANDON")
    abandonment_rate = (abandons / joins) if joins else 0.0

    revenue = (
        db.query(PosTransactionRecord)
        .filter(PosTransactionRecord.store_id == store_id)
        .filter(PosTransactionRecord.timestamp >= start)
        .filter(PosTransactionRecord.timestamp < end)
        .with_entities(PosTransactionRecord.basket_value_inr)
        .all()
    )
    total_revenue = sum(row[0] for row in revenue)

    return StoreMetrics(
        store_id=store_id,
        window_start=start,
        window_end=end,
        unique_visitors=unique_count,
        conversion_rate=round(conversion_rate, 4),
        avg_dwell_by_zone=zone_metrics,
        queue_depth=queue_depth,
        abandonment_rate=round(abandonment_rate, 4),
        total_revenue_inr=round(total_revenue, 2),
    )
