from __future__ import annotations

import re
import subprocess
from typing import Dict, Any
from pathlib import Path
import os

import tomli

from .const import mydir

ansi_escape_re = re.compile(r'\x1B(\[[0-?]*[ -/]*[@-~]|\(B)')

def kill_child_processes() -> None:
  subprocess.run(['kill_children'])

def read_config() -> Dict[str, Any]:
  selfdir = Path(__file__).resolve().parent.parent
  config_file_candidates = [mydir / 'config.toml', selfdir / 'config.toml']
  for config_file in config_file_candidates:
    # ConfigParser.read does not raise an exception is the file is missing
    if config_file.exists():
      with open(config_file, 'rb') as f:
        return tomli.load(f)
  else:
    raise Exception('No config files found!')

def reap_zombies() -> None:
  # reap any possible dead children since we are a subreaper
  try:
    while os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG) is not None:
      pass
  except ChildProcessError:
    pass

