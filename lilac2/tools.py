import os
import re
import subprocess
import signal

ansi_escape_re = re.compile(r'\x1B(\[[0-?]*[ -/]*[@-~]|\(B)')

def kill_child_processes() -> None:
  pids = subprocess.check_output(
    ['pid_children', str(os.getpid())]
  ).decode().split()
  for pid in pids:
    try:
      os.kill(int(pid), signal.SIGKILL)
    except OSError:
      pass
