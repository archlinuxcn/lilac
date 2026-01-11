import re
import subprocess
from typing import Dict, Any
import os
import logging
from contextlib import suppress
import time

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

def get_cpu_idle() -> tuple[int, int]:
  with open('/proc/stat') as f:
    line = f.readline()
    numbers = [int(x) for x in line.split()[1:]]
    return numbers[3], sum(numbers)

def get_running_task_cpu_ratio() -> float:
  a = get_cpu_idle()
  time.sleep(1)
  b = get_cpu_idle()
  idle = (b[0] - a[0]) / (b[1] - a[1])
  return 1 - idle

def get_avail_memory() -> int:
  with open('/proc/meminfo') as f:
    for l in f:
      if l.startswith('MemAvailable:'):
        return int(l.split()[1]) * 1024
  return 10 *  1024 ** 3

if __name__ == '__main__':
  cpu = get_running_task_cpu_ratio()
  mem = get_avail_memory()
  print(cpu, mem)
