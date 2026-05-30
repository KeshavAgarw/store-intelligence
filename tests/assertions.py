"""Sample assertions referenced in the challenge problem statement."""

from __future__ import annotations

import httpx


def run_assertions(base_url: str = "http://localhost:8000") -> None:
    client = httpx.Client(base_url=base_url, timeout=30.0)

    health = client.get("/health")
    assert health.status_code == 200, health.text
    assert health.json()["database"] == "connected"

    metrics = client.get("/stores/STORE_BLR_002/metrics")
    assert metrics.status_code == 200, metrics.text
    body = metrics.json()
    assert body["store_id"] == "STORE_BLR_002"
    assert body["unique_visitors"] >= 0
    assert 0.0 <= body["conversion_rate"] <= 1.0

    funnel = client.get("/stores/STORE_BLR_002/funnel")
    assert funnel.status_code == 200
    assert len(funnel.json()["stages"]) == 4

    heatmap = client.get("/stores/STORE_BLR_002/heatmap")
    assert heatmap.status_code == 200
    assert heatmap.json()["data_confidence"] in {"high", "low"}

    anomalies = client.get("/stores/STORE_BLR_002/anomalies")
    assert anomalies.status_code == 200
    assert isinstance(anomalies.json()["anomalies"], list)

    print("All sample assertions passed.")


if __name__ == "__main__":
    run_assertions()
