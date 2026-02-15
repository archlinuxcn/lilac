from __future__ import annotations

import logging
import json
import sys
import os

from ..vendor.nicelogger import enable_pretty_logging

from ..tools import kill_child_processes, read_config
from ..cmd import run_cmd
from ..workerman import WorkerManager

logger = logging.getLogger(__name__)

def main() -> None:
  enable_pretty_logging('DEBUG')

  config = read_config()
  os.environ.update(config.get('envvars', ()))

  input = json.load(sys.stdin)
  logger.debug('[remote.worker] got input: %r', input)
  workerman = WorkerManager.from_name(config, input.pop('workerman'))
  worker_no = input['worker_no']
  # make remote process to exit 60s earlier so that we could do some cleanup
  deadline = input.pop('deadline') - 60
  myresultpath = input.pop('result')

  # remove previous locally built packages
  run_cmd(["sh", "-c", "rm -f -- *.pkg.tar.xz *.pkg.tar.xz.sig *.pkg.tar.zst *.pkg.tar.zst.sig"])

  remote_r = {'status': 'done', 'version': None}
  r = {}
  try:
    pkgname = os.path.basename(os.getcwd())
    remote_r = workerman.run_remote(pkgname, deadline, worker_no, input)
    workerman.fetch_files(pkgname)
  except Exception as e:
    r = {
      'status': 'failed',
      'msg': repr(e),
    }
    sys.stdout.flush()
  except KeyboardInterrupt:
    logger.info('KeyboardInterrupt received')
    r = {
      'status': 'failed',
      'msg': 'KeyboardInterrupt',
    }
  finally:
    # say goodbye to all our children
    kill_child_processes()

  with open(myresultpath, 'w') as f:
    remote_r.update(r)
    json.dump(remote_r, f)

if __name__ == '__main__':
  main()
