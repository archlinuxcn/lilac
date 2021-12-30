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

from . import pkgbuild
from .typing import LilacMod
from .nvchecker import NvResults
from .packages import Dependency
from .api import notify_maintainers
from .tools import kill_child_processes
from .nomypy import BuildResult # type: ignore
from .const import _G
from .cmd import run_cmd

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
  destdir: str,
  logfile: Path,
  pythonpath: List[str],
) -> tuple[BuildResult, Optional[str]]:
  '''return BuildResult and version string if successful'''
  start_time = time.time()
  pkg_version = None
  rusage = None
  try:
    _G.mod = mod
    _G.epoch = _G.pkgver = _G.pkgrel = None
    maintainer = repo.find_maintainers(mod)[0]
    time_limit_hours = getattr(mod, 'time_limit_hours', 1)
    os.environ['PACKAGER'] = '%s (on behalf of %s) <%s>' % (
      myname, maintainer.name, maintainer.email)

    depend_packages = resolve_depends(repo, depends)
    pkgdir = repo.repodir / pkgbase
    try:
      rusage, error = call_worker(
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

    staging = getattr(mod, 'staging', False)
    if staging:
      destdir = os.path.join(destdir, 'staging')
      if not os.path.isdir(destdir):
        os.mkdir(destdir)
    sign_and_copy(destdir)
    if staging:
      notify_maintainers('软件包已被置于 staging 目录，请查验后手动发布。')
      result = BuildResult.staged()
    else:
      result = BuildResult.successful()

    # mypy thinks they are None...
    assert _G.pkgver is not None
    assert _G.pkgrel is not None
    pkg_version = pkgbuild.format_package_version(_G.epoch, _G.pkgver, _G.pkgrel)

  except SkipBuild as e:
    result = BuildResult.skipped(e.msg)
  except BuildFailed as e:
    result = BuildResult.failed(e.msg)
  except Exception as e:
    result = BuildResult.failed(e)
  finally:
    del _G.mod, _G.epoch, _G.pkgver, _G.pkgrel

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

def sign_and_copy(dest: str) -> None:
  pkgs = [x for x in os.listdir() if x.endswith(('.pkg.tar.xz', '.pkg.tar.zst'))]
  for pkg in pkgs:
    run_cmd(['gpg', '--pinentry-mode', 'loopback', '--passphrase', '',
             '--detach-sign', '--', pkg])
  for f in os.listdir():
    if not f.endswith(('.pkg.tar.xz', '.pkg.tar.xz.sig', '.pkg.tar.zst', '.pkg.tar.zst.sig')):
      continue
    try:
      os.link(f, os.path.join(dest, f))
    except FileExistsError:
      pass

def call_worker(
  pkgbase: str,
  pkgdir: Path,
  logfile: Path,
  depend_packages: List[str],
  update_info: NvResults,
  bindmounts: List[str],
  deadline: float,
  pythonpath: List[str],
) -> tuple[None, Optional[Exception]]:
  input = {
    'depend_packages': depend_packages,
    'update_info': update_info.to_list(),
    'bindmounts': bindmounts,
  }
  fd, resultpath = tempfile.mkstemp(prefix=pkgbase, suffix='.lilac')
  os.close(fd)
  input['result'] = resultpath

  cmd = [sys.executable, '-m', 'lilac2.worker', pkgbase]
  env = os.environ.copy()
  env['PYTHONPATH'] = ':'.join(pythonpath)
  with logfile.open('wb') as logf:
    p = subprocess.Popen(
      cmd,
      stdin = subprocess.PIPE,
      stdout = logf,
      stderr = logf,
      cwd = pkgdir,
      env = env,
    )
  p.stdin.write(json.dumps(input).encode()) # type: ignore
  p.stdin.close() # type: ignore

  while True:
    try:
      p.wait(10)
    except subprocess.TimeoutExpired:
      if time.time() > deadline:
        kill_child_processes()
    else:
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

      break

  st = r['status']
  error: Optional[Exception]
  if st == 'done':
    error = None
  elif st == 'skipped':
    error = SkipBuild(r['msg'])
  elif st == 'failed':
    error = BuildFailed(r['msg'])
  else:
    error = RuntimeError('unknown status from worker', st)
  return None, error
