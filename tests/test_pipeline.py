# PROMPT: Write unit tests for pipeline event emission helpers and polygon zone checks.
# CHANGES MADE: Added frame timestamp test and polygon inclusion edge cases.

from datetime import datetime, timezone

from pipeline.emit import PipelineEvent, frame_timestamp, write_events
from pipeline.tracker import point_in_polygon


def test_frame_timestamp_offsets():
    start = datetime(2026, 3, 3, 10, 0, tzinfo=timezone.utc)
    ts = frame_timestamp(start, frame_index=30, fps=15.0)
    assert ts == datetime(2026, 3, 3, 10, 0, 2, tzinfo=timezone.utc)


def test_pipeline_event_schema_fields():
    event = PipelineEvent(
        store_id="STORE_BLR_002",
        camera_id="CAM_ENTRY_01",
        visitor_id="VIS_000001",
        event_type="ENTRY",
        timestamp=datetime(2026, 3, 3, 14, 0, tzinfo=timezone.utc),
        confidence=0.9,
    )
    payload = event.to_dict()
    assert payload["event_type"] == "ENTRY"
    assert payload["timestamp"].endswith("Z")
    assert payload["metadata"]["session_seq"] is None


def test_point_in_polygon():
    square = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    assert point_in_polygon(0.5, 0.5, square) is True
    assert point_in_polygon(1.5, 0.5, square) is False


def test_write_events_jsonl(tmp_path):
    events = [
        PipelineEvent(
            store_id="STORE_BLR_002",
            camera_id="CAM_ENTRY_01",
            visitor_id="VIS_000001",
            event_type="ENTRY",
            timestamp=datetime(2026, 3, 3, 14, 0, tzinfo=timezone.utc),
            confidence=0.9,
            metadata={"session_seq": 1},
        )
    ]
    out = tmp_path / "events.jsonl"
    write_events(events, out)
    content = out.read_text(encoding="utf-8").strip()
    assert '"event_type": "ENTRY"' in content
