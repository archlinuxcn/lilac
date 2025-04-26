from __future__ import annotations

import re
import subprocess
from typing import Dict, Any
import os
import logging
from contextlib import suppress

import tomllib

from .const import mydir

logger = logging.getLogger(__name__)

ansi_escape_re = re.compile(r'\x1B(\[[0-?]*[ -/]*[@-~]|\(B)')

def kill_child_processes() -> None:
  logger.debug('killing child processes (if any)')
  subprocess.run(['kill_children'])

def read_config() -> Dict[str, Any]:
  config_file = mydir / 'config.toml'
  with open(config_file, 'rb') as f:
    return tomllib.load(f)

def reap_zombies() -> None:
  # reap any possible dead children since we are a subreaper
  with suppress(ChildProcessError):
    while os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG) is not None:
      pass

def get_avail_cpu_percent() -> float:
  ncpu = os.process_cpu_count()
  running = 0
  with open('/proc/stat') as f:
    for l in f:
      if l.startswith('procs_running '):
        running = int(l.split()[1])
        break
  if ncpu and running:
    return running / ncpu
  else:
    return 0.0

def get_avail_memory() -> int:
  with open('/proc/stat') as f:
    for l in f:
      if l.startswith('MemAvailable:'):
        return int(l.split()[1]) * 1024
  return 10 *  1024 ** 3
