from aiohttp import web

async def get_current(request):
  raise NotImplementedError

async def watch_update(request):
  raise NotImplementedError

def setup_app(app):
  app.router.add_get('/building/current', get_current)
  app.router.add_get('/building/watch', watch_update)

def main():
  import argparse

  from .vendor.nicelogger import enable_pretty_logging

  parser = argparse.ArgumentParser(
    description = 'HTTP services for build.archlinuxcn.org',
  )
  parser.add_argument('--port', default=9008, type=int,
                      help='port to listen on')
  parser.add_argument('--ip', default='127.0.0.1',
                      help='address to listen on')
  parser.add_argument('--loglevel', default='info',
                      choices=['debug', 'info', 'warn', 'error'],
                      help='log level')
  args = parser.parse_args()

  enable_pretty_logging(args.loglevel.upper())

  app = web.Application()
  setup_app(app)

  web.run_app(app, host=args.ip, port=args.port)

if __name__ == '__main__':
  main()
