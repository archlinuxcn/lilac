from __future__ import annotations

import os
import sys
import logging
import subprocess
from typing import (
  Optional, Iterable, List, Set, TYPE_CHECKING,
)
import tempfile
from pathlib import Path
import time
import json
import threading
import signal
from contextlib import suppress

from .typing import LilacInfo, Cmd, RUsage
from .nvchecker import NvResults
from .packages import Dependency
from .tools import reap_zombies
from .nomypy import BuildResult # type: ignore
from . import systemd

if TYPE_CHECKING:
  from .repo import Repo
  assert Repo # type: ignore # make pyflakes happy
  del Repo

logger = logging.getLogger(__name__)
TLS = threading.local()

class MissingDependencies(Exception):
  def __init__(self, pkgs: Set[str]) -> None:
    self.deps = pkgs

class SkipBuild(Exception):
  def __init__(self, msg: str) -> None:
    self.msg = msg

class BuildFailed(Exception):
  def __init__(self, msg: str) -> None:
    self.msg = msg

def build_package(
  pkgbase: str,
  lilacinfo: LilacInfo,
  bindmounts: list[str],
  tmpfs: list[str],
  update_info: NvResults,
  depends: Iterable[Dependency],
  repo: Repo,
  myname: str,
  destdir: Path,
  logfile: Path,
) -> tuple[BuildResult, Optional[str]]:
  '''return BuildResult and version string if successful'''
  start_time = time.time()
  pkg_version = None
  rusage = None
  try:
    maintainer = repo.find_maintainers(lilacinfo)[0]
    time_limit_hours = lilacinfo.time_limit_hours
    packager = '%s (on behalf of %s) <%s>' % (
      myname, maintainer.name, maintainer.email)

    depend_packages = resolve_depends(repo, depends)
    pkgdir = repo.repodir / pkgbase
    try:
      pkg_version, rusage, error = call_worker(
        pkgbase = pkgbase,
        pkgdir = pkgdir,
        depend_packages = [str(x) for x in depend_packages],
        update_info = update_info,
        bindmounts = bindmounts,
        tmpfs = tmpfs,
        logfile = logfile,
        deadline = start_time + time_limit_hours * 3600,
        packager = packager,
      )
      if error:
        raise error
    finally:
      may_need_cleanup()
      reap_zombies()

    staging = lilacinfo.staging
    if staging:
      destdir = destdir / 'staging'
      if not destdir.is_dir():
        destdir.mkdir()
    sign_and_copy(pkgdir, destdir)
    if staging:
      notify_maintainers(
        repo, lilacinfo,
        f'{pkgbase} {pkg_version} is just packaged',
        'The package has been placed in the staging directory, please manually check it before publishing it.',
      )
      result = BuildResult.staged()
    else:
      result = BuildResult.successful()

  except SkipBuild as e:
    result = BuildResult.skipped(e.msg)
  except BuildFailed as e:
    result = BuildResult.failed(e.msg)
  except Exception as e:
    logger.exception('build failed with exception')
    result = BuildResult.failed(e)

  elapsed = time.time() - start_time
  result.rusage = rusage
  result.elapsed = elapsed
  with logfile.open('a') as f:
    t = time.strftime('%Y-%m-%d %H:%M:%S %z')
    print(
      f'\n[{t}] build (version {pkg_version}) finished in {int(elapsed)}s with result: {result!r}',
      file = f,
    )
  return result, pkg_version

def resolve_depends(repo: Optional[Repo], depends: Iterable[Dependency]) -> List[str]:
  need_build_first = set()
  depend_packages = []

  for x in depends:
    p = x.resolve()
    if p is None:
      if repo is None or not repo.manages(x):
        # ignore depends that are not in repo
        continue
      need_build_first.add(x.pkgname)
    else:
      depend_packages.append(str(p))

  if need_build_first:
    raise MissingDependencies(need_build_first)
  logger.info('depends: %s, resolved: %s', depends, depend_packages)

  return depend_packages

def may_need_cleanup() -> None:
  st = os.statvfs('/var/lib/archbuild')
  if st.f_bavail * st.f_bsize < 60 * 1024 ** 3:
    subprocess.check_call(['sudo', 'build-cleaner'])

def sign_and_copy(pkgdir: Path, dest: Path) -> None:
  pkgs = [x for x in pkgdir.iterdir() if x.name.endswith(('.pkg.tar.xz', '.pkg.tar.zst'))]
  for pkg in pkgs:
    subprocess.run([
      'gpg', '--pinentry-mode', 'loopback',
       '--passphrase', '', '--detach-sign', '--', pkg,
    ])
  for f in pkgdir.iterdir():
    if not f.name.endswith(('.pkg.tar.xz', '.pkg.tar.xz.sig', '.pkg.tar.zst', '.pkg.tar.zst.sig')):
      continue
    with suppress(FileExistsError):
      (dest / f.name).hardlink_to(f)

def notify_maintainers(
  repo: Repo, lilacinfo: LilacInfo,
  subject: str, body: str,
) -> None:
  maintainers = repo.find_maintainers(lilacinfo)
  addresses = [str(x) for x in maintainers]
  repo.sendmail(addresses, subject, body)

def call_worker(
  pkgbase: str,
  pkgdir: Path,
  logfile: Path,
  depend_packages: List[str],
  update_info: NvResults,
  bindmounts: list[str],
  tmpfs: list[str],
  deadline: float,
  packager: str,
) -> tuple[Optional[str], RUsage, Optional[Exception]]:
  '''
  return: package version, resource usage, error information
  '''
  input = {
    'depend_packages': depend_packages,
    'update_info': update_info.to_list(),
    'bindmounts': bindmounts,
    'tmpfs': tmpfs,
    'logfile': str(logfile), # for sending error reports
    'worker_no': TLS.worker_no,
  }
  fd, resultpath = tempfile.mkstemp(prefix=f'{pkgbase}-', suffix='.lilac')
  os.close(fd)
  input['result'] = resultpath
  input_bytes = json.dumps(input).encode()
  logger.debug('worker input: %r', input_bytes)

  cmd = [sys.executable, '-u', '-m', 'lilac2.worker', pkgbase]
  if systemd.available():
    _call_cmd = _call_cmd_systemd
  else:
    _call_cmd = _call_cmd_subprocess
  name = f'lilac-worker-{TLS.worker_no}'
  rusage, timedout = _call_cmd(
    name, cmd, logfile, pkgdir, deadline,
    input_bytes, packager,
  )

  try:
    with open(resultpath) as f:
      r = json.load(f)
    logger.debug('received from worker: %r', r)
  except json.decoder.JSONDecodeError:
    r = {
      'status': 'failed',
      'msg': 'worker did not return a proper result!',
      'version': None,
    }
  finally:
    with suppress(FileNotFoundError):
      os.unlink(resultpath)

  st = r['status']

  error: Optional[Exception]
  if timedout:
    error = TimeoutError()
  elif st == 'done':
    error = None
  elif st == 'skipped':
    error = SkipBuild(r['msg'])
  elif st == 'failed':
    error = BuildFailed(r['msg'])
  else:
    error = RuntimeError('unknown status from worker', st)

  version = r['version']
  return version, rusage, error

def _call_cmd_subprocess(
  name: str,
  cmd: Cmd,
  logfile: Path,
  pkgdir: Path,
  deadline: float,
  input: bytes,
  packager: str,
) -> tuple[RUsage, bool]:
  '''call cmd as a subprocess'''
  timedout = False
  env = os.environ.copy()
  env['PACKAGER'] = packager
  with logfile.open('wb') as logf:
    p = subprocess.Popen(
      cmd,
      stdin = subprocess.PIPE,
      stdout = logf,
      stderr = logf,
      cwd = pkgdir,
      env = env,
    )
  p.stdin.write(input) # type: ignore
  p.stdin.close() # type: ignore

  while True:
    try:
      p.wait(10)
    except subprocess.TimeoutExpired:
      if time.time() > deadline:
        timedout = True
        # we need to rely on worker to kill child processes
        p.send_signal(signal.SIGINT)
        try:
          p.wait(3)
        except subprocess.TimeoutExpired:
          p.kill()
    else:
      break

  return RUsage(0, 0), timedout

def _call_cmd_systemd(
  name: str,
  cmd: Cmd,
  logfile: Path,
  pkgdir: Path,
  deadline: float,
  input: bytes,
  packager: str,
) -> tuple[RUsage, bool]:
  '''run cmd with systemd-run and collect resource usage'''
  with logfile.open('wb') as logf:
    p = systemd.start_cmd(
      name,
      cmd,
      stdin = subprocess.PIPE,
      stdout = logf,
      stderr = logf,
      cwd = pkgdir,
      setenv = {
        'PATH': os.environ['PATH'], # we've updated our PATH
        'MAKEFLAGS': os.environ.get('MAKEFLAGS', ''),
        'PACKAGER': packager,
      },
    )
  p.stdin.write(input) # type: ignore
  p.stdin.close() # type: ignore

  return systemd.poll_rusage(name, deadline)

