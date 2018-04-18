import os
import subprocess
import signal

def kill_child_processes():
  pids = subprocess.check_output(
    ['pid_children', str(os.getpid())]
  ).decode().split()
  for pid in pids:
    try:
      os.kill(int(pid), signal.SIGKILL)
    except OSError:
      pass

def is_nodejs_thing():
  with open('PKGBUILD') as f:
    data = f.read()
    return 'nodejs' in data and 'npm' in data

