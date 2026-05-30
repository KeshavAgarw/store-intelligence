"""Main detection script: process CCTV clips and emit structured events."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import cv2

from pipeline.emit import write_events
from pipeline.tracker import SessionTracker

try:
    from ultralytics import YOLO
except ImportError:  # pragma: no cover
    YOLO = None


def parse_clip_start(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_layout(layout_path: Path) -> dict:
    with layout_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def process_clip(
    clip_path: Path,
    store_id: str,
    camera: dict,
    model_name: str,
    frame_stride: int,
    max_frames: int | None,
) -> list:
    if YOLO is None:
        raise RuntimeError("ultralytics is required. Install with: pip install ultralytics")

    model = YOLO(model_name)
    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open clip: {clip_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    clip_start = parse_clip_start(camera["clip_start"])
    tracker = SessionTracker(store_id, camera["camera_id"], clip_start, fps, camera)

    frame_index = 0
    processed = 0
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        if frame_index % frame_stride != 0:
            frame_index += 1
            continue

        results = model.track(frame, persist=True, classes=[0], verbose=False)
        detections: list[tuple[int, float, float, float, float, float]] = []
        if results and results[0].boxes is not None and results[0].boxes.id is not None:
            boxes = results[0].boxes
            for box, track_id, conf in zip(boxes.xyxy, boxes.id, boxes.conf):
                tid = int(track_id.item())
                detections.append(
                    (
                        tid,
                        float(conf.item()),
                        float(box[0].item()),
                        float(box[1].item()),
                        float(box[2].item()),
                        float(box[3].item()),
                    )
                )

        tracker.update(frame_index, detections, frame.shape[:2])
        processed += 1
        frame_index += 1
        if max_frames and processed >= max_frames:
            break

    cap.release()
    return tracker.events


def main() -> None:
    parser = argparse.ArgumentParser(description="Process CCTV clips into structured store events.")
    parser.add_argument("--clips", default="CCTV Footage", help="Directory containing MP4 clips")
    parser.add_argument("--layout", default="data/store_layout.json", help="Store layout JSON path")
    parser.add_argument("--out", default="output/events.jsonl", help="Output JSONL path")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLO weights")
    parser.add_argument("--frame-stride", type=int, default=2, help="Process every Nth frame")
    parser.add_argument("--max-frames", type=int, default=None, help="Limit frames per clip (dev mode)")
    args = parser.parse_args()

    layout = load_layout(Path(args.layout))
    clips_dir = Path(args.clips)
    all_events = []

    for store in layout["stores"]:
        store_id = store["store_id"]
        for camera in store["cameras"]:
            clip_path = clips_dir / camera["clip_file"]
            if not clip_path.exists():
                print(f"Skipping missing clip: {clip_path}")
                continue
            print(f"Processing {clip_path.name} ({camera['camera_id']})...")
            events = process_clip(
                clip_path,
                store_id,
                camera,
                args.model,
                args.frame_stride,
                args.max_frames,
            )
            all_events.extend(events)
            print(f"  emitted {len(events)} events")

    write_events(all_events, Path(args.out))
    print(f"Wrote {len(all_events)} events to {args.out}")


if __name__ == "__main__":
    main()
