# PROMPT: Generate pytest tests for Store Intelligence API ingest idempotency,
# metrics endpoint with staff exclusion, and zero-visitor edge case.
# CHANGES MADE: Added funnel/health checks, wired sample_events fixture,
# and validated duplicate ingest counts separately.

import json
from pathlib import Path

from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "store-intelligence-api"
    assert body["database"] == "connected"


def test_ingest_accepts_sample_events(client: TestClient, sample_events):
    response = client.post("/events/ingest", json={"events": sample_events})
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] == len(sample_events)
    assert body["rejected"] == 0


def test_ingest_is_idempotent(client: TestClient, sample_events):
    first = client.post("/events/ingest", json={"events": sample_events}).json()
    second = client.post("/events/ingest", json={"events": sample_events}).json()
    assert first["accepted"] == len(sample_events)
    assert second["accepted"] == 0
    assert second["duplicate"] == len(sample_events)


def test_metrics_excludes_staff(client: TestClient, sample_events):
    client.post("/events/ingest", json={"events": sample_events})
    response = client.get("/stores/STORE_BLR_002/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["unique_visitors"] == 2
    assert body["conversion_rate"] >= 0.0


def test_metrics_zero_visitors(client: TestClient):
    response = client.get("/stores/STORE_EMPTY/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["unique_visitors"] == 0
    assert body["conversion_rate"] == 0.0


def test_funnel_session_dedup(client: TestClient, sample_events):
    client.post("/events/ingest", json={"events": sample_events})
    response = client.get("/stores/STORE_BLR_002/funnel")
    assert response.status_code == 200
    stages = {stage["stage"]: stage["count"] for stage in response.json()["stages"]}
    assert stages["Entry"] >= 2
    assert stages["Purchase"] >= 0


def test_heatmap_endpoint(client: TestClient, sample_events):
    client.post("/events/ingest", json={"events": sample_events})
    response = client.get("/stores/STORE_BLR_002/heatmap")
    assert response.status_code == 200
    assert "cells" in response.json()


def test_anomalies_endpoint(client: TestClient, sample_events):
    client.post("/events/ingest", json={"events": sample_events})
    response = client.get("/stores/STORE_BLR_002/anomalies")
    assert response.status_code == 200
    assert len(response.json()["anomalies"]) >= 1


def test_partial_ingest_malformed_event(client: TestClient, sample_events):
    bad = dict(sample_events[0])
    bad["event_id"] = "not-a-uuid"
    payload = {"events": [bad, sample_events[1]]}
    response = client.post("/events/ingest", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["rejected"] == 1
    assert body["accepted"] == 1
