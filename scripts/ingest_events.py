"""Helper script to ingest JSONL events into the running API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx


def chunked(items: list, size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="output/events.jsonl")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    events = []
    with Path(args.file).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    with httpx.Client(timeout=60.0) as client:
        for batch in chunked(events, args.batch_size):
            response = client.post(f"{args.api}/events/ingest", json={"events": batch})
            response.raise_for_status()
            print(response.json())


if __name__ == "__main__":
    main()
