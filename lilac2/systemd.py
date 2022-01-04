import os
import subprocess
from typing import ParamSpec, Generator
import select
import time
import logging

from .typing import Cmd, RUsage

_available = None
logger = logging.getLogger(__name__)

def available() -> bool:
  global _available

  if _available is None:
    _available = _check_availability()
  return _available

def _check_availability() -> bool:
  if 'DBUS_SESSION_BUS_ADDRESS' not in os.environ:
    dbus = f'/run/user/{os.getuid()}/bus'
    if not os.path.exists(dbus):
      return False
    os.environ['DBUS_SESSION_BUS_ADDRESS'] = f'unix:path={dbus}'
  p = subprocess.run(['systemd-run', '--quiet', '--user', '-u', 'lilac-check', 'true'])
  return p.returncode == 0

P = ParamSpec('P')

def start_cmd(
  name: str, cmd: Cmd,
  setenv: dict[str, str] = {},
  **kwargs: P.kwargs, # type: ignore
) -> subprocess.Popen:
  cmd_s: Cmd = [
    'systemd-run', '--pipe', '--quiet', '--user',
    '--wait', '--remain-after-exit', '--collect',
    '-u', name,
  ]

  if cwd := kwargs.pop('cwd', None):
    cmd_s += [f'--working-directory={str(cwd)}'] # type: ignore

  cmd_setenv = [f'--setenv={k}={v}' for k, v in setenv.items()]
  cmd_s = cmd_s + cmd_setenv + ['--'] + cmd # type: ignore
  logger.debug('running %s', subprocess.list2cmdline(cmd_s))
  return subprocess.Popen(cmd_s, **kwargs)

def _get_service_info(name: str) -> tuple[int, str, str]:
  '''return pid and control group path'''
  out = subprocess.check_output([
    'systemctl', '--user', 'show', f'{name}.service',
    '--property=MainPID',
    '--property=ControlGroup',
    '--property=SubState',
  ], text=True)
  pid = 0
  cgroup = ''
  state = ''
  for l in out.splitlines():
    k, v = l.split('=', 1)
    if k == 'MainPID':
      pid = int(v)
    elif k == 'ControlGroup':
      cgroup = v
    elif k == 'SubState':
      state = v
  return pid, cgroup, state

def _poll_cmd(pid: int) -> Generator[None, None, None]:
  try:
    pidfd = os.pidfd_open(pid) # type: ignore
  except OSError as e:
    if e.errno == 22:
      return

  poll = select.poll()
  poll.register(pidfd, select.POLLIN)

  try:
    while True:
      ret = poll.poll(1_000)
      if ret:
        logger.debug('worker exited')
        return
      yield
  finally:
    os.close(pidfd)

def poll_rusage(name: str, deadline: float) -> tuple[RUsage, bool]:
  timedout = False
  done_state = ['exited', 'failed']
  while True:
    pid, cgroup, state = _get_service_info(name)
    if (not pid or not cgroup) and state not in done_state:
      logger.debug('%s.service state: %s, waiting', name, state)
      time.sleep(0.1)
    else:
      break

  try:
    if state in done_state:
      logger.warning('%s.service already finished: %s', name, state)
      return RUsage(0, 0), False

    mem_file = f'/sys/fs/cgroup{cgroup}/memory.current'
    cpu_file = f'/sys/fs/cgroup{cgroup}/cpu.stat'

    mem_max = 0
    for _ in _poll_cmd(pid):
      with open(mem_file) as f:
        mem_cur = int(f.read().rstrip())
        mem_max = max(mem_cur, mem_max)
      if time.time() > deadline:
        timedout = True
        break

    with open(cpu_file) as f:
      for l in f:
        if l.startswith('usage_usec '):
          usec = int(l.split(None, 1)[-1])

  finally:
    if timedout:
      logger.debug('killing worker service')
      subprocess.run(['systemctl', '--user', 'kill', '--signal=SIGKILL', name])
    else:
      logger.debug('stopping worker service')
      subprocess.run(['systemctl', '--user', 'stop', '--quiet', name])
  return RUsage(usec / 1_000_000, mem_max), timedout
