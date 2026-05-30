#!/usr/bin/env bash
set -euo pipefail
python -m pipeline.detect --clips "CCTV Footage" --layout data/store_layout.json --out output/events.jsonl "$@"
