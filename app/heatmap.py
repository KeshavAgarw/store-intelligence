"""Zone heatmap metrics."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.analytics_utils import customer_events, day_window, fetch_store_events, sessions_from_events
from app.models import HeatmapCell, StoreHeatmap


def compute_heatmap(db: Session, store_id: str) -> StoreHeatmap:
    start, end = day_window()
    events = fetch_store_events(db, store_id, start, end)
    sessions = sessions_from_events(events)

    visit_freq: dict[str, int] = defaultdict(int)
    dwell_values: dict[str, list[int]] = defaultdict(list)

    for event in customer_events(events):
        if not event.zone_id:
            continue
        if event.event_type == "ZONE_ENTER":
            visit_freq[event.zone_id] += 1
        if event.event_type == "ZONE_DWELL" and event.dwell_ms:
            dwell_values[event.zone_id].append(event.dwell_ms)

    max_visits = max(visit_freq.values(), default=0)
    cells: list[HeatmapCell] = []
    for zone_id in sorted(set(visit_freq) | set(dwell_values)):
        visits = visit_freq.get(zone_id, 0)
        dwells = dwell_values.get(zone_id, [])
        avg_dwell = (sum(dwells) / len(dwells)) if dwells else 0.0
        score = round((visits / max_visits) * 100, 2) if max_visits else 0.0
        cells.append(
            HeatmapCell(
                zone_id=zone_id,
                visit_frequency=visits,
                avg_dwell_ms=round(avg_dwell, 2),
                score=score,
            )
        )

    confidence = "high" if len(sessions) >= 20 else "low"
    return StoreHeatmap(store_id=store_id, cells=cells, data_confidence=confidence)
