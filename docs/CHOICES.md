# Engineering Choices — Store Intelligence

## 1. Detection Model: YOLOv8n + ByteTrack

**Options considered**
- YOLOv8n / YOLOv8s with ByteTrack (Ultralytics native)
- RT-DETR for higher accuracy at lower FPS
- MediaPipe for lightweight CPU-only detection

**What AI suggested**
Claude recommended YOLOv8s with DeepSORT for retail person tracking, citing better re-ID across occlusions.

**What I chose and why**
YOLOv8n with Ultralytics' integrated ByteTrack. On a developer laptop, 20-minute 1080p clips are expensive to process; the nano model with `frame_stride=2` keeps iteration time reasonable while still detecting individuals in group entries. ByteTrack avoids a separate tracking dependency. I rejected DeepSORT for now because it adds integration complexity without guaranteed gains on blurred/anonymised footage.

**Trade-off**
Lower recall on partial occlusions near billing displays. Mitigation: emit low-confidence events instead of filtering them out.

---

## 2. Event Schema Design

**Options considered**
- Flat schema exactly as specified in the problem statement
- Extended schema with raw bbox coordinates in metadata
- Separate tables for sessions vs events in the pipeline output

**What AI suggested**
Store bounding boxes and track IDs in metadata for debugging and post-hoc Re-ID evaluation.

**What I chose and why**
Strict adherence to the required schema with only the specified metadata fields (`queue_depth`, `sku_zone`, `session_seq`). This ensures ingest validation passes and scoring harness compatibility. Session state lives in the tracker, not in emitted events — the API reconstructs sessions from the event stream, which matches how production event buses typically work.

**Trade-off**
Harder to debug individual detections without re-running the pipeline. Acceptable for submission; debug fields could be added behind a `--debug` flag later.

---

## 3. API Architecture: SQLite + Session-Based Funnel

**Options considered**
- SQLite (embedded, zero-config)
- PostgreSQL (production-grade, better concurrency)
- In-memory store with periodic flush

**What AI suggested**
PostgreSQL in Docker Compose for "production realism."

**What I chose and why**
SQLite with SQLAlchemy. The acceptance gate requires `docker compose up` with no manual DB setup; SQLite satisfies that with minimal moving parts. Funnel logic uses visitor-level session reconstruction rather than counting raw events — this prevents re-entry and duplicate zone visits from inflating conversion numbers. POS correlation uses a 5-minute window before each transaction timestamp, matching the problem statement.

**Trade-off**
SQLite won't scale to 40 live stores with concurrent writes. For the challenge scope (batch ingest + query), it's sufficient. Migration path: change `DATABASE_URL` to Postgres with no code changes beyond connection string.

---

## 4. Metrics Reference Date

**Options considered**
- Always use UTC "today"
- Derive window from earliest/latest event in DB
- Environment variable for challenge clip date

**What I chose**
`METRICS_REFERENCE_DATE` environment variable, defaulting to today but set to `2026-03-03` in Docker Compose and tests. This aligns metrics with POS transactions and sample events without hardcoding dates in business logic.
