# Store Intelligence

End-to-end Store Intelligence system for the Purplle Tech Challenge: CCTV detection pipeline → structured events → analytics API.

## Quick start (5 commands)

```bash
git clone <your-repo-url>
cd store-intelligence
docker compose up -d --build
curl http://localhost:8000/health
python scripts/ingest_events.py --file data/sample_events.jsonl
curl http://localhost:8000/stores/STORE_BLR_002/metrics
```

## Local development (without Docker)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:METRICS_REFERENCE_DATE = "2026-03-03T12:00:00Z"
uvicorn app.main:app --reload
```

## Run detection pipeline

Process all CCTV clips and write events to `output/events.jsonl`:

```powershell
pip install ultralytics opencv-python-headless
python -m pipeline.detect --clips "CCTV Footage" --layout data/store_layout.json --out output/events.jsonl
```

Dev mode (first 300 frames per clip):

```powershell
python -m pipeline.detect --clips "CCTV Footage" --max-frames 300 --frame-stride 3
```

Ingest pipeline output into the API:

```powershell
python scripts/ingest_events.py --file output/events.jsonl
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/events/ingest` | Batch ingest up to 500 events (idempotent by `event_id`) |
| GET | `/stores/{id}/metrics` | Visitors, conversion, dwell, queue, abandonment |
| GET | `/stores/{id}/funnel` | Entry → Zone → Billing → Purchase funnel |
| GET | `/stores/{id}/heatmap` | Zone frequency and dwell scores (0–100) |
| GET | `/stores/{id}/anomalies` | Queue spike, conversion drop, dead zones |
| GET | `/health` | Service and per-store feed freshness |

## Tests

```powershell
$env:METRICS_REFERENCE_DATE = "2026-03-03T12:00:00Z"
pytest --cov=app --cov=pipeline --cov-report=term-missing
```

## Project layout

```
app/          FastAPI intelligence API
pipeline/     YOLOv8 detection + tracking + event emission
data/         store_layout.json, POS CSV, sample events
tests/        API and pipeline unit tests
docs/         DESIGN.md, CHOICES.md
```

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `sqlite:///./data/store.db` | Event storage |
| `DATA_DIR` | `data` | Layout and POS files |
| `METRICS_REFERENCE_DATE` | today (UTC) | Metrics window for challenge clips |
