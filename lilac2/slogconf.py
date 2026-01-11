from __future__ import annotations

import time

import structlog
from structlog.types import WrappedLogger, EventDict

def exc_info(
  logger: WrappedLogger, level: str, event: EventDict,
) -> EventDict:
  if level == 'exception' and 'exc_info' not in event:
    event['exc_info'] = True
  return event

_renderer = structlog.processors.JSONRenderer(
  ensure_ascii=False)

def json_renderer(logger: WrappedLogger, level: str, event: EventDict) -> str | bytes:
  event['level'] = level
  return _renderer(logger, level, event)

def add_timestamp(
  logger: WrappedLogger, level: str, event: EventDict,
) -> EventDict:
  event['ts'] = time.time()
  return event

