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

from .typing import LilacMod, PkgVers, Cmd, RUsage
from .nvchecker import NvResults
from .packages import Dependency
from .tools import kill_child_processes
from .nomypy import BuildResult # type: ignore
from .const import _G
from .cmd import run_cmd
from . import systemd

if TYPE_CHECKING:
  from .repo import Repo
  assert Repo # make pyflakes happy
  del Repo

logger = logging.getLogger(__name__)

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
  mod: LilacMod,
  bindmounts: List[str],
  update_info: NvResults,
  depends: Iterable[Dependency],
  repo: Repo,
  myname: str,
  destdir: Path,
  logfile: Path,
  pythonpath: str,
) -> tuple[BuildResult, Optional[str]]:
  '''return BuildResult and version string if successful'''
  start_time = time.time()
  pkg_version = None
  rusage = None
  try:
    _G.mod = mod
    maintainer = repo.find_maintainers(mod)[0]
    time_limit_hours = getattr(mod, 'time_limit_hours', 1)
    os.environ['PACKAGER'] = '%s (on behalf of %s) <%s>' % (
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
        logfile = logfile,
        deadline = start_time + time_limit_hours * 3600,
        pythonpath = pythonpath,
      )
      if error:
        raise error
    finally:
      kill_child_processes()
      may_need_cleanup()
      reap_zombies()

    staging = getattr(mod, 'staging', False)
    if staging:
      destdir = destdir / 'staging'
      if not destdir.is_dir():
        destdir.mkdir()
    sign_and_copy(pkgdir, destdir)
    if staging:
      subject = f'{pkgbase} {pkg_version} 刚刚打包了'
      notify_maintainers(subject, '软件包已被置于 staging 目录，请查验后手动发布。')
      result = BuildResult.staged()
    else:
      result = BuildResult.successful()

  except SkipBuild as e:
    result = BuildResult.skipped(e.msg)
  except BuildFailed as e:
    result = BuildResult.failed(e.msg)
  except Exception as e:
    result = BuildResult.failed(e)
  finally:
    del _G.mod

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
    run_cmd(['gpg', '--pinentry-mode', 'loopback', '--passphrase', '',
             '--detach-sign', '--', pkg])
  for f in pkgdir.iterdir():
    if not f.name.endswith(('.pkg.tar.xz', '.pkg.tar.xz.sig', '.pkg.tar.zst', '.pkg.tar.zst.sig')):
      continue
    try:
      (dest / f.name).hardlink_to(f)
    except FileExistsError:
      pass

def notify_maintainers(subject: str, body: str) -> None:
  repo = _G.repo
  maintainers = repo.find_maintainers(_G.mod)
  addresses = [str(x) for x in maintainers]
  repo.sendmail(addresses, subject, body)

def call_worker(
  pkgbase: str,
  pkgdir: Path,
  logfile: Path,
  depend_packages: List[str],
  update_info: NvResults,
  bindmounts: List[str],
  deadline: float,
  pythonpath: str,
) -> tuple[Optional[str], RUsage, Optional[Exception]]:
  '''
  return: package verion, resource usage, error information
  '''
  input = {
    'depend_packages': depend_packages,
    'update_info': update_info.to_list(),
    'bindmounts': bindmounts,
    'logfile': str(logfile), # for sending error reports
  }
  fd, resultpath = tempfile.mkstemp(prefix=pkgbase, suffix='.lilac')
  os.close(fd)
  input['result'] = resultpath
  input_bytes = json.dumps(input).encode()

  cmd = [sys.executable, '-u', '-m', 'lilac2.worker', pkgbase]
  if systemd.available():
    _call_cmd = _call_cmd_systemd
  else:
    _call_cmd = _call_cmd_subprocess
  rusage, timedout = _call_cmd(
    cmd, pythonpath, logfile, pkgdir, deadline, input_bytes,
  )

  try:
    with open(resultpath) as f:
      r = json.load(f)
  except json.decoder.JSONDecodeError:
    r = {
      'status': 'failed',
      'msg': 'worker did not return a proper result!',
    }
  finally:
    try:
      os.unlink(resultpath)
    except FileNotFoundError:
      pass

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

  vers = r['pkgvers']
  if vers:
    version = str(PkgVers(*vers))
  else:
    version = None
  return version, rusage, error

def _call_cmd_subprocess(
  cmd: Cmd,
  pythonpath: str,
  logfile: Path,
  pkgdir: Path,
  deadline: float,
  input: bytes,
) -> tuple[RUsage, bool]:
  '''call cmd as a subprocess'''
  timedout = False
  env = os.environ.copy()
  env['PYTHONPATH'] = pythonpath
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
        kill_child_processes()
    else:
      break

  return RUsage(0, 0), timedout

def _call_cmd_systemd(
  cmd: Cmd,
  pythonpath: str,
  logfile: Path,
  pkgdir: Path,
  deadline: float,
  input: bytes,
) -> tuple[RUsage, bool]:
  '''run cmd with systemd-run and collect resource usage'''
  with logfile.open('wb') as logf:
    p = systemd.start_cmd(
      'lilac-worker',
      cmd,
      stdin = subprocess.PIPE,
      stdout = logf,
      stderr = logf,
      cwd = pkgdir,
      setenv = {'PYTHONPATH': pythonpath},
    )
  p.stdin.write(input) # type: ignore
  p.stdin.close() # type: ignore

  return systemd.poll_rusage('lilac-worker', deadline)

def reap_zombies() -> None:
  # reap any possible dead children since we are a subreaper
  try:
    while os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG) is not None:
      pass
  except ChildProcessError:
    pass

