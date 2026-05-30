"""Event schema builders and JSONL emission."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass
class PipelineEvent:
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: str
    timestamp: datetime
    zone_id: str | None = None
    dwell_ms: int = 0
    is_staff: bool = False
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        ts = self.timestamp.astimezone(timezone.utc).replace(microsecond=0)
        return {
            "event_id": self.event_id,
            "store_id": self.store_id,
            "camera_id": self.camera_id,
            "visitor_id": self.visitor_id,
            "event_type": self.event_type,
            "timestamp": ts.isoformat().replace("+00:00", "Z"),
            "zone_id": self.zone_id,
            "dwell_ms": self.dwell_ms,
            "is_staff": self.is_staff,
            "confidence": round(self.confidence, 4),
            "metadata": {
                "queue_depth": self.metadata.get("queue_depth"),
                "sku_zone": self.metadata.get("sku_zone"),
                "session_seq": self.metadata.get("session_seq"),
            },
        }


def frame_timestamp(clip_start: datetime, frame_index: int, fps: float) -> datetime:
    offset = timedelta(seconds=frame_index / max(fps, 1.0))
    return clip_start.astimezone(timezone.utc) + offset


def write_events(events: list[PipelineEvent], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event.to_dict()) + "\n")


def load_events_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events
