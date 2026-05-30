# Design Document — Store Intelligence

## Overview

This system converts raw retail CCTV footage into actionable store analytics. The architecture follows a classic event-driven pattern: a computer-vision pipeline emits structured behavioural events, and a FastAPI service ingests those events to compute real-time metrics, funnels, heatmaps, and anomalies.

```
CCTV Clips → YOLOv8 + ByteTrack → Session Tracker → JSONL Events
                                                          ↓
                                              POST /events/ingest
                                                          ↓
                                              SQLite Event Store
                                                          ↓
                                    Metrics / Funnel / Heatmap / Anomalies
```

## Detection Layer

Each camera clip is processed independently with YOLOv8n for person detection and Ultralytics' built-in ByteTrack integration for multi-object tracking. Camera roles from `store_layout.json` drive behaviour:

- **Entry camera**: line-crossing logic emits `ENTRY` / `EXIT`
- **Floor cameras**: polygon zones emit `ZONE_ENTER`, `ZONE_EXIT`, and periodic `ZONE_DWELL`
- **Billing camera**: queue depth estimation and `BILLING_QUEUE_*` events

Staff are heuristically flagged when bounding-box height exceeds a threshold (uniform / counter-height proxy). Staff events are still stored but excluded from customer analytics.

## Event Stream

Events conform to the challenge schema with UUID v4 IDs, ISO-8601 UTC timestamps derived from clip start + frame offset, and metadata for queue depth and session sequencing. Low-confidence detections are retained with their actual confidence score rather than being silently dropped.

## Intelligence API

The API uses SQLite for simplicity and portability. Ingestion validates events with Pydantic, deduplicates on `event_id`, and supports partial success. Analytics modules share helper functions for session grouping, staff exclusion, and POS correlation (5-minute billing window before transaction timestamp).

Metrics use a configurable reference date (`METRICS_REFERENCE_DATE`) so challenge footage dated 2026-03-03 aligns with POS records. Health checks report per-store `STALE_FEED` when the last event is older than 10 minutes.

## Production Considerations

- Structured request logging with trace IDs
- Database errors return HTTP 503 without stack traces
- Docker Compose single-command startup
- Idempotent ingest verified in tests

## AI-Assisted Decisions

1. **Model selection**: An LLM recommended YOLOv8n + ByteTrack as the default stack for 1080p/15fps retail CCTV. I agreed — it balances speed and integration (tracking built into Ultralytics). I overrode the suggestion to use a larger model (YOLOv8m) because clip processing time matters on a laptop CPU; frame stride compensates.

2. **Staff detection**: AI suggested a VLM for uniform classification. I chose a simpler bbox-height heuristic for the MVP because it runs offline without API costs and can be swapped later. Documented as a known limitation in CHOICES.md.

3. **Metrics date window**: AI initially used `datetime.now()` for "today's metrics", which broke on historical challenge clips. I added `METRICS_REFERENCE_DATE` after testing ingest with sample events — a case where human verification caught a logic bug the generated code missed.
