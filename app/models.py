"""Pydantic schemas for events and API responses."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"
    BILLING_QUEUE_JOIN = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"
    REENTRY = "REENTRY"


class EventMetadata(BaseModel):
    queue_depth: int | None = None
    sku_zone: str | None = None
    session_seq: int | None = None


class StoreEvent(BaseModel):
    event_id: str
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: EventType
    timestamp: datetime
    zone_id: str | None = None
    dwell_ms: int = 0
    is_staff: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: EventMetadata = Field(default_factory=EventMetadata)

    @field_validator("event_id")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        UUID(value, version=4)
        return value


class IngestRequest(BaseModel):
    events: list[dict[str, Any]] = Field(max_length=500)


class IngestError(BaseModel):
    event_id: str | None = None
    error: str


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    duplicate: int
    errors: list[IngestError]


class ZoneMetric(BaseModel):
    zone_id: str
    avg_dwell_ms: float
    visit_count: int


class StoreMetrics(BaseModel):
    store_id: str
    window_start: datetime
    window_end: datetime
    unique_visitors: int
    conversion_rate: float
    avg_dwell_by_zone: list[ZoneMetric]
    queue_depth: int
    abandonment_rate: float
    total_revenue_inr: float


class FunnelStage(BaseModel):
    stage: str
    count: int
    drop_off_pct: float | None = None


class StoreFunnel(BaseModel):
    store_id: str
    stages: list[FunnelStage]


class HeatmapCell(BaseModel):
    zone_id: str
    visit_frequency: int
    avg_dwell_ms: float
    score: float


class StoreHeatmap(BaseModel):
    store_id: str
    cells: list[HeatmapCell]
    data_confidence: Literal["high", "low"]


class AnomalySeverity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


class Anomaly(BaseModel):
    anomaly_type: str
    severity: AnomalySeverity
    message: str
    suggested_action: str
    detected_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class StoreAnomalies(BaseModel):
    store_id: str
    anomalies: list[Anomaly]


class StoreHealth(BaseModel):
    store_id: str
    last_event_at: datetime | None
    status: Literal["OK", "STALE_FEED"]


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    service: str
    stores: list[StoreHealth]
    database: Literal["connected", "unavailable"]
