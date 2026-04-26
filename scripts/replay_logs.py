#!/usr/bin/env python3
"""CLI script to replay raw logs via the /replay/logs endpoint."""
from __future__ import annotations

import argparse
import sys

import httpx


def main():
    parser = argparse.ArgumentParser(description="Replay SignalThrottle logs")
    parser.add_argument("file", help="Path to log file")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the service",
    )
    args = parser.parse_args()

    with open(args.file, "r") as f:
        logs = f.read()

    resp = httpx.post(
        f"{args.url}/replay/logs",
        json={"logs": logs},
        timeout=60,
    )
    print(resp.json())


if __name__ == "__main__":
    main()
