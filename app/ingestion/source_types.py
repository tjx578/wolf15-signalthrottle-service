from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    WEBHOOK = "webhook"
    REPLAY = "replay"
    LOG_SCRAPE = "log_scrape"
