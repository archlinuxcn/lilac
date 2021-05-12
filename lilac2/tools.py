from __future__ import annotations

import os
import re
import subprocess
import contextlib
from typing import Generator, Dict, Any, cast
from pathlib import Path

import toml

from .const import mydir

ansi_escape_re = re.compile(r'\x1B(\[[0-?]*[ -/]*[@-~]|\(B)')

def kill_child_processes() -> None:
  subprocess.run(['kill_children'])

@contextlib.contextmanager
def redirect_output(fd: int) -> Generator[None, None, None]:
  old_stdout = os.dup(1)
  old_stderr = os.dup(2)
  os.dup2(fd, 1)
  os.dup2(fd, 2)
  try:
    yield
  finally:
    os.dup2(old_stdout, 1)
    os.dup2(old_stderr, 2)
    os.close(old_stdout)
    os.close(old_stderr)

def read_config() -> Dict[str, Any]:
  selfdir = Path(__file__).resolve().parent.parent
  config_file_candidates = [mydir / 'config.toml', selfdir / 'config.toml']
  for config_file in config_file_candidates:
    # ConfigParser.read does not raise an exception is the file is missing
    if config_file.exists():
      with open(config_file) as f:
        return cast(Dict[str, Any], toml.load(f))
  else:
    raise Exception('No config files found!')

