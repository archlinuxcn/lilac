from __future__ import annotations

import structlog
import time
from typing import Dict, Any

LogEvent = Dict[str, Any]


def exc_info(logger, level: str, event: LogEvent,) -> LogEvent:
    if level == "exception" and "exc_info" not in event:
        event["exc_info"] = True
    return event


_renderer = structlog.processors.JSONRenderer(ensure_ascii=False)


def json_renderer(logger, level: str, event: LogEvent) -> str:
    event["level"] = level
    return _renderer(logger, level, event)


def add_timestamp(logger, level: str, event: LogEvent,) -> LogEvent:
    event["ts"] = time.time()
    return event
