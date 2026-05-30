"""Tracking, visitor sessions, and behavioural event generation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pipeline.emit import PipelineEvent, frame_timestamp


def point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


@dataclass
class TrackState:
    track_id: int
    visitor_id: str | None = None
    session_seq: int = 0
    last_cx: float = 0.0
    last_cy: float = 0.0
    prev_cy: float = 0.0
    active_zones: set[str] = field(default_factory=set)
    zone_enter_times: dict[str, datetime] = field(default_factory=dict)
    last_dwell_emit: dict[str, datetime] = field(default_factory=dict)
    has_entered: bool = False
    has_exited: bool = False
    in_billing: bool = False
    is_staff: bool = False
    confidence_sum: float = 0.0
    confidence_count: int = 0
    history_y: list[float] = field(default_factory=list)

    @property
    def avg_confidence(self) -> float:
        return self.confidence_sum / max(self.confidence_count, 1)


class SessionTracker:
    def __init__(self, store_id: str, camera_id: str, clip_start: datetime, fps: float, config: dict[str, Any]):
        self.store_id = store_id
        self.camera_id = camera_id
        self.clip_start = clip_start
        self.fps = fps
        self.config = config
        self.tracks: dict[int, TrackState] = {}
        self.visitor_counter = 0
        self.events: list[PipelineEvent] = []
        self.role = config.get("role", "floor")
        self.entry_line_y = config.get("entry_line", {}).get("y_ratio", 0.55)
        self.direction_in = config.get("entry_line", {}).get("direction_in", "down")
        self.zones = config.get("zones", [])

    def _new_visitor_id(self) -> str:
        self.visitor_counter += 1
        return f"VIS_{self.visitor_counter:06d}"

    def _ensure_track(self, track_id: int) -> TrackState:
        if track_id not in self.tracks:
            self.tracks[track_id] = TrackState(track_id=track_id)
        return self.tracks[track_id]

    def _emit(
        self,
        track: TrackState,
        event_type: str,
        frame_index: int,
        zone_id: str | None = None,
        dwell_ms: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not track.visitor_id and event_type not in {"ENTRY", "REENTRY"}:
            return
        track.session_seq += 1
        self.events.append(
            PipelineEvent(
                store_id=self.store_id,
                camera_id=self.camera_id,
                visitor_id=track.visitor_id or self._new_visitor_id(),
                event_type=event_type,
                timestamp=frame_timestamp(self.clip_start, frame_index, self.fps),
                zone_id=zone_id,
                dwell_ms=dwell_ms,
                is_staff=track.is_staff,
                confidence=min(track.avg_confidence, 1.0),
                metadata={"session_seq": track.session_seq, **(metadata or {})},
            )
        )

    def update(
        self,
        frame_index: int,
        detections: list[tuple[int, float, float, float, float, float]],
        frame_shape: tuple[int, int],
    ) -> None:
        height, width = frame_shape
        billing_count = 0

        for track_id, conf, x1, y1, x2, y2 in detections:
            track = self._ensure_track(track_id)
            cx = (x1 + x2) / 2 / width
            cy = (y1 + y2) / 2 / height
            track.confidence_sum += conf
            track.confidence_count += 1
            track.history_y.append(cy)
            if len(track.history_y) > 8:
                track.history_y.pop(0)

            bbox_height = (y2 - y1) / height
            if bbox_height > 0.45 and conf > 0.5:
                track.is_staff = True

            if self.role == "entry" and track.visitor_id is None:
                crossed = self._crossed_entry_line(track, cy)
                if crossed == "in":
                    track.visitor_id = self._new_visitor_id()
                    track.has_entered = True
                    track.has_exited = False
                    self._emit(track, "ENTRY", frame_index)
                elif crossed == "out" and track.has_entered and not track.has_exited:
                    track.has_exited = True
                    self._emit(track, "EXIT", frame_index)

            if track.visitor_id:
                self._process_zones(track, cx, cy, frame_index)

            if self.role == "billing" and track.in_billing:
                billing_count += 1

            track.prev_cy = track.last_cy
            track.last_cx, track.last_cy = cx, cy

        if self.role == "billing" and billing_count:
            for track in self.tracks.values():
                if track.in_billing and track.visitor_id:
                    meta = {"queue_depth": max(billing_count - 1, 0), "sku_zone": "BILLING"}
                    if track.session_seq == 0 or not any(
                        event.event_type == "BILLING_QUEUE_JOIN" and event.visitor_id == track.visitor_id
                        for event in self.events[-3:]
                    ):
                        if billing_count > 1:
                            self._emit(track, "BILLING_QUEUE_JOIN", frame_index, zone_id="BILLING", metadata=meta)

    def _crossed_entry_line(self, track: TrackState, cy: float) -> str | None:
        if len(track.history_y) < 2:
            return None
        prev_y, curr_y = track.history_y[-2], track.history_y[-1]
        line = self.entry_line_y
        if self.direction_in == "down":
            if prev_y < line <= curr_y:
                return "in"
            if prev_y > line >= curr_y:
                return "out"
        else:
            if prev_y > line >= curr_y:
                return "in"
            if prev_y < line <= curr_y:
                return "out"
        return None

    def _process_zones(self, track: TrackState, cx: float, cy: float, frame_index: int) -> None:
        current_zones: set[str] = set()
        for zone in self.zones:
            polygon = zone["polygon_ratio"]
            if point_in_polygon(cx, cy, polygon):
                current_zones.add(zone["zone_id"])

        entered = current_zones - track.active_zones
        exited = track.active_zones - current_zones
        now = frame_timestamp(self.clip_start, frame_index, self.fps)

        for zone_id in entered:
            track.zone_enter_times[zone_id] = now
            track.last_dwell_emit[zone_id] = now
            meta = {"sku_zone": zone_id}
            self._emit(track, "ZONE_ENTER", frame_index, zone_id=zone_id, metadata=meta)
            if zone_id == "BILLING":
                track.in_billing = True

        for zone_id in exited:
            start = track.zone_enter_times.pop(zone_id, None)
            track.last_dwell_emit.pop(zone_id, None)
            self._emit(track, "ZONE_EXIT", frame_index, zone_id=zone_id)
            if zone_id == "BILLING":
                track.in_billing = False
                if track.has_entered:
                    self._emit(track, "BILLING_QUEUE_ABANDON", frame_index, zone_id="BILLING")

        for zone_id in current_zones:
            start = track.zone_enter_times.get(zone_id)
            last_emit = track.last_dwell_emit.get(zone_id)
            if start and last_emit:
                elapsed_ms = int((now - last_emit).total_seconds() * 1000)
                if elapsed_ms >= 30_000:
                    track.last_dwell_emit[zone_id] = now
                    total_ms = int((now - start).total_seconds() * 1000)
                    self._emit(
                        track,
                        "ZONE_DWELL",
                        frame_index,
                        zone_id=zone_id,
                        dwell_ms=total_ms,
                        metadata={"sku_zone": zone_id},
                    )

        track.active_zones = current_zones
