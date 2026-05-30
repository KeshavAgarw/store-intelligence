"""Operational anomaly detection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.analytics_utils import (
    customer_events,
    day_window,
    ensure_utc,
    fetch_store_events,
    load_pos_transactions,
    parse_metadata,
    unique_visitors,
)
from app.database import PosTransactionRecord
from app.metrics import compute_metrics
from app.models import Anomaly, AnomalySeverity, StoreAnomalies


def compute_anomalies(db: Session, store_id: str) -> StoreAnomalies:
    load_pos_transactions(db)
    now = datetime.now(timezone.utc)
    start, end = day_window()
    events = fetch_store_events(db, store_id, start, end)
    metrics = compute_metrics(db, store_id)
    anomalies: list[Anomaly] = []

    if metrics.queue_depth >= 4:
        anomalies.append(
            Anomaly(
                anomaly_type="BILLING_QUEUE_SPIKE",
                severity=AnomalySeverity.CRITICAL if metrics.queue_depth >= 6 else AnomalySeverity.WARN,
                message=f"Billing queue depth is {metrics.queue_depth}, above normal threshold.",
                suggested_action="Open an additional billing counter or deploy floor staff to assist queue.",
                detected_at=now,
                metadata={"queue_depth": metrics.queue_depth},
            )
        )

    week_start = start - timedelta(days=7)
    historical_events = fetch_store_events(db, store_id, week_start, start)
    historical_visitors = len(unique_visitors(historical_events))
    historical_days = max((start - week_start).days, 1)
    avg_daily_visitors = historical_visitors / historical_days if historical_visitors else 0
    today_visitors = metrics.unique_visitors

    if avg_daily_visitors >= 5 and today_visitors < avg_daily_visitors * 0.5:
        anomalies.append(
            Anomaly(
                anomaly_type="CONVERSION_DROP",
                severity=AnomalySeverity.WARN,
                message="Visitor volume is significantly below the recent 7-day average.",
                suggested_action="Review in-store promotions and verify camera feeds are healthy.",
                detected_at=now,
                metadata={"today_visitors": today_visitors, "avg_daily_visitors": round(avg_daily_visitors, 2)},
            )
        )

    if metrics.conversion_rate < 0.05 and today_visitors >= 10:
        anomalies.append(
            Anomaly(
                anomaly_type="CONVERSION_DROP",
                severity=AnomalySeverity.WARN,
                message=f"Conversion rate {metrics.conversion_rate:.2%} is unusually low for current traffic.",
                suggested_action="Inspect billing zone staffing and queue abandonment patterns.",
                detected_at=now,
                metadata={"conversion_rate": metrics.conversion_rate},
            )
        )

    zone_last_seen: dict[str, datetime] = {}
    for event in customer_events(events):
        if event.zone_id and event.event_type in {"ZONE_ENTER", "ZONE_DWELL"}:
            zone_last_seen[event.zone_id] = ensure_utc(event.timestamp)

    for zone_id, last_seen in zone_last_seen.items():
        if now - last_seen >= timedelta(minutes=30):
            anomalies.append(
                Anomaly(
                    anomaly_type="DEAD_ZONE",
                    severity=AnomalySeverity.INFO,
                    message=f"Zone {zone_id} has had no visits for over 30 minutes.",
                    suggested_action="Verify merchandising placement and consider a zone-specific promotion.",
                    detected_at=now,
                    metadata={"zone_id": zone_id, "last_seen": last_seen.isoformat()},
                )
            )

    if not anomalies:
        anomalies.append(
            Anomaly(
                anomaly_type="NONE",
                severity=AnomalySeverity.INFO,
                message="No active anomalies detected.",
                suggested_action="Continue monitoring store metrics.",
                detected_at=now,
            )
        )

    return StoreAnomalies(store_id=store_id, anomalies=anomalies)
