import sys
import json
import subprocess
import logging
import tempfile
import os

from .. import systemd
from ..vendor.nicelogger import enable_pretty_logging

logger = logging.getLogger(__name__)

def main() -> None:
  enable_pretty_logging('DEBUG')

  input = json.load(sys.stdin)
  logger.debug('[remote.runner] got input: %r', input)

  name = input.pop('name')
  deadline = input.pop('deadline')
  myresultpath = input.pop('result')

  cmd = [
    sys.executable,
    '-Xno_debug_ranges', # save space
    '-P', # don't prepend cwd to sys.path where unexpected directories may exist
    '-m', 'lilac2.worker',
  ] + sys.argv[1:]

  fd, resultpath = tempfile.mkstemp(prefix='remoterunner-', suffix='.lilac')
  os.close(fd)
  input['result'] = resultpath

  setenv = input.pop('setenv')
  if v := os.environ.get('MAKEFLAGS'):
    setenv['MAKEFLAGS'] = v
  else:
    cores = os.process_cpu_count()
    if cores is not None:
      setenv['MAKEFLAGS'] = '-j{0}'.format(cores)

  p = systemd.start_cmd(
    name,
    cmd,
    stdin = subprocess.PIPE,
    cwd = input.pop('pkgdir'),
    setenv = setenv,
  )
  p.stdin.write(json.dumps(input).encode()) # type: ignore
  p.stdin.close() # type: ignore

  rusage, _ = systemd.poll_rusage(name, deadline)
  p.wait()

  with open(resultpath, 'rb') as f:
    r = json.load(f)
  r['rusage'] = rusage

  with open(myresultpath, 'w') as f2:
    json.dump(r, f2)

if __name__ == '__main__':
  main()
