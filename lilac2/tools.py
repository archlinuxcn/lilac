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
