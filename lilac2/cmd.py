from __future__ import annotations

import os
import logging
import subprocess
import signal
import sys
import re
from subprocess import CalledProcessError
from typing import Optional
import types

from .typing import Cmd
from .tools import kill_child_processes

logger = logging.getLogger(__name__)

def git_pull() -> bool:
  """
  git pull from upstream
  :return: false if already up to date, true otherwise
  """
  output = run_cmd(['git', 'pull', '--no-edit'])
  return 'up-to-date' not in output

def git_push() -> None:
  """
  pushes changes to upstream, rebase if upstream has changed
  :return:
  """
  while True:
    try:
      run_cmd(['git', 'push'])
      break
    except CalledProcessError as e:
      if 'non-fast-forward' in e.output or 'fetch first' in e.output:
        run_cmd(["git", "pull", "--rebase"])
      else:
        raise

def git_reset_hard() -> None:
  """
  hard resets git repo to HEAD
  :return:
  """
  run_cmd(['git', 'reset', '--hard'])

def get_git_branch() -> str:
  """
  gets the current git branch
  :return:
  """
  out = subprocess.check_output(
    ['git', 'branch', '--no-color'], universal_newlines = True)
  for line in out.splitlines():
    if line.startswith('* '):
      return line.split(None, 1)[-1]

  return '(unknown branch)'

def run_cmd(cmd: Cmd, *, use_pty: bool = False, silent: bool = False,
            cwd: Optional[os.PathLike] = None) -> str:
  """
  runs the command
  :param cmd: command (List with the first elem being exe path and the rest being args)
  :param use_pty:
  :param silent:
  :param cwd: command working directory
  :return:
  """
  logger.debug('running %r, %susing pty,%s showing output', cmd,
               '' if use_pty else 'not ',
               ' not' if silent else '')
  if use_pty:
    rfd, stdout = os.openpty()
    stdin = stdout
    # for fd leakage
    logger.debug('pty master fd=%d, slave fd=%d.', rfd, stdout)
  else:
    stdin = subprocess.DEVNULL
    stdout = subprocess.PIPE

  try:
    exited = False
    def child_exited(signum: int, sigframe: types.FrameType) -> None:
      nonlocal exited
      exited = True
    old_hdl = signal.signal(signal.SIGCHLD, child_exited)

    p = subprocess.Popen(
      cmd, stdin = stdin, stdout = stdout, stderr = subprocess.STDOUT,
      cwd = cwd,
    )
    if use_pty:
      os.close(stdout)
    else:
      rfd = p.stdout.fileno()
    out = []
    outlen = 0

    while True:
      try:
        r = os.read(rfd, 4096)
        if not r:
          if exited:
            break
          else:
            continue
      except InterruptedError:
        continue
      except OSError as e:
        if e.errno == 5: # Input/output error: no clients run
          break
        else:
          raise
      r = r.replace(b'\x0f', b'') # ^O
      if not silent:
        sys.stderr.buffer.write(r)
      out.append(r)
      outlen += len(r)
      if outlen > 1024 ** 3: # larger than 1G
        kill_child_processes()

    code = p.wait()
    if old_hdl is not None:
      signal.signal(signal.SIGCHLD, old_hdl)

    outb = b''.join(out)
    outs = outb.decode('utf-8', errors='replace')
    outs = outs.replace('\r\n', '\n')
    outs = re.sub(r'.*\r', '', outs)
    if outlen > 1024 ** 3: # larger than 1G
      outs += '\n\n输出过多，已击杀。\n'
    if code != 0:
        raise subprocess.CalledProcessError(code, cmd, outs)
    return outs
  finally:
    if use_pty:
      os.close(rfd)

def pkgrel_changed(from_: str, to: str, pkgname: str) -> bool:
  """
  check if the package's pkgrel has been changed between commits
  :param from_: older commit
  :param to: newer commit
  :param pkgname: name of the package
  :return: true if pkgrel has been changed, false otherwise
  """
  cmd = ["git", "diff", "-p", from_, to, '--', pkgname + '/PKGBUILD']
  r = run_cmd(cmd, silent=True).splitlines()
  return any(x.startswith('+pkgrel=') for x in r)

