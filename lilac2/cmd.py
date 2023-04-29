from __future__ import annotations

import os
import logging
import subprocess
import signal
import sys
import re
from subprocess import CalledProcessError
from typing import Optional, Dict
import types
from pathlib import Path
from contextlib import suppress

from .typing import Cmd

logger = logging.getLogger(__name__)

def _find_gitroot() -> Path:
  d = Path('.').resolve(strict=True)
  while d != d.parent:
    if (d / '.git').exists():
      return d
    else:
      d = d.parent

  raise Exception('failed to find git root')

def git_pull() -> bool:
  output = run_cmd(['git', 'pull', '--no-edit'])
  return 'up-to-date' not in output

def git_pull_override() -> bool:
  try:
    env = os.environ.copy()
    env['LANG'] = 'en_US.UTF-8'
    with suppress(KeyError):
      del env['LANGUAGE']
    output = run_cmd(
      ['git', 'pull', '--no-edit'],
      env = env,
    )
  except subprocess.CalledProcessError as e:
    if 'would be overwritten by merge:' in e.output:
      files = [line.strip()
                for line in e.output.splitlines()
                if line.startswith('\t')]
      gitroot = _find_gitroot()
      for f in files:
        (gitroot / f).unlink()
      output = run_cmd(['git', 'pull', '--no-edit'])
    else:
      raise

  return 'up-to-date' not in output

def git_push() -> None:
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
  run_cmd(['git', 'reset', '--hard'])

def get_git_branch() -> str:
  out = subprocess.check_output(
    ['git', 'branch', '--no-color'], universal_newlines = True)
  for line in out.splitlines():
    if line.startswith('* '):
      return line.split(None, 1)[-1]

  return '(unknown branch)'

def run_cmd(
  cmd: Cmd, *,
  use_pty: bool = False,
  silent: bool = False,
  cwd: Optional[os.PathLike] = None,
  env: Optional[Dict[str, str]] = None,
) -> str:
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
    def child_exited(signum: int, sigframe: Optional[types.FrameType]) -> None:
      nonlocal exited
      exited = True
    old_hdl = signal.signal(signal.SIGCHLD, child_exited)

    p = subprocess.Popen(
      cmd, stdin = stdin,
      stdout = stdout, stderr = subprocess.STDOUT,
      cwd = cwd, env = env,
    )
    if use_pty:
      os.close(stdout)
    else:
      assert p.stdout
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
        p.kill()

    code = p.wait()
    if old_hdl is not None:
      signal.signal(signal.SIGCHLD, old_hdl)

    outb = b''.join(out)
    outs = outb.decode('utf-8', errors='replace')
    outs = outs.replace('\r\n', '\n')
    outs = re.sub(r'.*\r', '', outs)
    if outlen > 1024 ** 3: # larger than 1G
      outs += '\n\nOutput is quite long, already kiled\n'
    if code != 0:
      # set output by keyword to avoid being included in repr()
      raise subprocess.CalledProcessError(code, cmd, output=outs)
    return outs
  finally:
    if use_pty:
      os.close(rfd)

def pkgrel_changed(from_: str, to: str, pkgname: str) -> bool:
  cmd = ["git", "diff", "-p", from_, to, '--', pkgname + '/PKGBUILD']
  r = run_cmd(cmd, silent=True).splitlines()
  return any(x.startswith('+pkgrel=') for x in r)

UNTRUSTED_PREFIX: Cmd = [
  'bwrap', '--unshare-all', '--ro-bind', '/', '/', '--tmpfs', '/home',
  '--tmpfs', '/run', '--die-with-parent',
  '--tmpfs', '/tmp', '--proc', '/proc', '--dev', '/dev',
]
