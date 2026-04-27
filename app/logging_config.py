from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(log_level)

    # Only attach the handler once — guard against being called multiple times
    # (e.g. at module import time in main.py and again inside the lifespan hook).
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        root.addHandler(handler)

    # Ensure Uvicorn's own loggers emit at INFO so that startup messages
    # ("Started server process", "Waiting for application startup", etc.)
    # are not treated as errors by Railway's log collector.
    for uvicorn_logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error", "uvicorn.server"):
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.setLevel(log_level)
        # Prevent Uvicorn from adding its own duplicate handlers on top of ours.
        uvicorn_logger.propagate = True
