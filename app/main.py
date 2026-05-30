"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.anomalies import compute_anomalies
from app.database import get_db, init_db
from app.funnel import compute_funnel
from app.health import compute_health
from app.heatmap import compute_heatmap
from app.ingestion import ingest_events
from app.metrics import compute_metrics
from app.models import (
    HealthResponse,
    IngestRequest,
    IngestResponse,
    StoreAnomalies,
    StoreFunnel,
    StoreHeatmap,
    StoreMetrics,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("store_intelligence")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Store Intelligence API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def structured_logging(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Trace-Id"] = trace_id
        return response
    finally:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        store_id = request.path_params.get("id", "-")
        event_count = "-"
        if request.url.path.endswith("/ingest"):
            event_count = request.headers.get("X-Event-Count", "-")
        logger.info(
            "trace_id=%s store_id=%s endpoint=%s latency_ms=%s event_count=%s status_code=%s",
            trace_id,
            store_id,
            request.url.path,
            latency_ms,
            event_count,
            status_code,
        )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(_request: Request, _exc: SQLAlchemyError):
    return JSONResponse(
        status_code=503,
        content={
            "error": "database_unavailable",
            "message": "Database is temporarily unavailable. Retry shortly.",
        },
    )


def _handle_db(fn, db: Session):
    try:
        return fn(db)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@app.post("/events/ingest", response_model=IngestResponse)
def post_events_ingest(payload: IngestRequest, db: Session = Depends(get_db)) -> IngestResponse:
    return _handle_db(lambda session: ingest_events(session, payload), db)


@app.get("/stores/{store_id}/metrics", response_model=StoreMetrics)
def get_store_metrics(store_id: str, db: Session = Depends(get_db)) -> StoreMetrics:
    return _handle_db(lambda session: compute_metrics(session, store_id), db)


@app.get("/stores/{store_id}/funnel", response_model=StoreFunnel)
def get_store_funnel(store_id: str, db: Session = Depends(get_db)) -> StoreFunnel:
    return _handle_db(lambda session: compute_funnel(session, store_id), db)


@app.get("/stores/{store_id}/heatmap", response_model=StoreHeatmap)
def get_store_heatmap(store_id: str, db: Session = Depends(get_db)) -> StoreHeatmap:
    return _handle_db(lambda session: compute_heatmap(session, store_id), db)


@app.get("/stores/{store_id}/anomalies", response_model=StoreAnomalies)
def get_store_anomalies(store_id: str, db: Session = Depends(get_db)) -> StoreAnomalies:
    return _handle_db(lambda session: compute_anomalies(session, store_id), db)


@app.get("/health", response_model=HealthResponse)
def get_health(db: Session = Depends(get_db)) -> HealthResponse:
    return _handle_db(lambda session: compute_health(session), db)
