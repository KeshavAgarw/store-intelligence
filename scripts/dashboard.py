"""Simple terminal dashboard polling live metrics (Part E bonus)."""

from __future__ import annotations

import argparse
import time

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--store", default="STORE_BLR_002")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    with httpx.Client(timeout=10.0) as client:
        while True:
            metrics = client.get(f"{args.api}/stores/{args.store}/metrics").json()
            health = client.get(f"{args.api}/health").json()
            print(
                f"[{metrics['store_id']}] visitors={metrics['unique_visitors']} "
                f"conversion={metrics['conversion_rate']:.2%} "
                f"queue={metrics['queue_depth']} "
                f"status={health['status']}"
            )
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
