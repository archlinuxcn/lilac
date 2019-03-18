import structlog

def exc_info(logger, level, event):
  if level == 'exception':
    event['exc_info'] = True
  return event

_renderer = structlog.processors.JSONRenderer(
  ensure_ascii=False)

def json_renderer(logger, level, event):
  event['level'] = level
  return _renderer(logger, level, event)

