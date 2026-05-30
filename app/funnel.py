"""Conversion funnel with session deduplication."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.analytics_utils import (
    converted_visitors,
    customer_events,
    day_window,
    fetch_store_events,
    load_pos_transactions,
    sessions_from_events,
)
from app.models import FunnelStage, StoreFunnel


def _session_reached_billing(session_events) -> bool:
    return any(
        event.event_type in {"BILLING_QUEUE_JOIN", "ZONE_ENTER", "ZONE_DWELL"}
        and event.zone_id == "BILLING"
        for event in session_events
    )


def _session_reached_zone(session_events) -> bool:
    return any(event.event_type in {"ZONE_ENTER", "ZONE_DWELL"} and event.zone_id for event in session_events)


def compute_funnel(db: Session, store_id: str) -> StoreFunnel:
    load_pos_transactions(db)
    start, end = day_window()
    events = fetch_store_events(db, store_id, start, end)
    sessions = sessions_from_events(events)

    entry_visitors: set[str] = set()
    zone_visitors: set[str] = set()
    billing_visitors: set[str] = set()

    for visitor_id, session_events in sessions.items():
        has_entry = any(event.event_type in {"ENTRY", "REENTRY"} for event in session_events)
        if has_entry:
            entry_visitors.add(visitor_id)
        if _session_reached_zone(session_events):
            zone_visitors.add(visitor_id)
        if _session_reached_billing(session_events):
            billing_visitors.add(visitor_id)

    converted = converted_visitors(db, store_id, events)

    entry_count = len(entry_visitors)
    zone_count = len(zone_visitors)
    billing_count = len(billing_visitors)
    purchase_count = len(converted)

    def drop_off(current: int, previous: int) -> float | None:
        if previous == 0:
            return None
        return round(((previous - current) / previous) * 100, 2)

    stages = [
        FunnelStage(stage="Entry", count=entry_count, drop_off_pct=None),
        FunnelStage(stage="Zone Visit", count=zone_count, drop_off_pct=drop_off(zone_count, entry_count)),
        FunnelStage(stage="Billing Queue", count=billing_count, drop_off_pct=drop_off(billing_count, zone_count)),
        FunnelStage(stage="Purchase", count=purchase_count, drop_off_pct=drop_off(purchase_count, billing_count)),
    ]
    return StoreFunnel(store_id=store_id, stages=stages)
