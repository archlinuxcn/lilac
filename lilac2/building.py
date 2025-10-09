from __future__ import annotations

import os
import logging
import subprocess
from typing import (
  Optional, Iterable, Set, TYPE_CHECKING,
)
import tempfile
from pathlib import Path
import time
import json
import signal
from contextlib import suppress

from .typing import LilacInfo, Cmd, RUsage, PkgToBuild, OnBuildVers
from .nvchecker import NvResults
from .packages import Dependency, get_built_package_files
from .tools import reap_zombies
from .nomypy import BuildResult # type: ignore
from . import systemd
from . import intl
from .workerman import WorkerManager

if TYPE_CHECKING:
  from .repo import Repo
  assert Repo # type: ignore # make pyflakes happy
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
  to_build: PkgToBuild,
  lilacinfo: LilacInfo,
  bindmounts: list[str],
  tmpfs: list[str],
  update_info: NvResults,
  commit_msg_template: str,
  depends: Iterable[Dependency],
  repo: Repo,
  myname: str,
  destdir: Path,
  logfile: Path,
  worker_no: int,
) -> tuple[BuildResult, Optional[str]]:
  '''return BuildResult and version string if successful'''
  start_time = time.time()
  pkg_version = None
  rusage = None
  pkgbase = to_build.pkgbase
  try:
    maintainer = repo.find_maintainers(lilacinfo)[0]
    time_limit_hours = lilacinfo.time_limit_hours
    packager = '%s (on behalf of %s) <%s>' % (
      myname, maintainer.name, maintainer.email)

    assert to_build.workerman is not None
    depend_packages = resolve_depends(repo, depends)
    to_build.workerman.sync_depended_packages(depend_packages)
    pkgdir = repo.repodir / pkgbase
    try:
      pkg_version, rusage, error = call_worker(
        repo = repo,
        lilacinfo = lilacinfo,
        pkgbase = pkgbase,
        pkgdir = pkgdir,
        depend_packages = depend_packages,
        update_info = update_info,
        on_build_vers = to_build.on_build_vers,
        bindmounts = bindmounts,
        commit_msg_template = commit_msg_template,
        tmpfs = tmpfs,
        logfile = logfile,
        deadline = start_time + time_limit_hours * 3600,
        packager = packager,
        worker_no = worker_no,
        workerman = to_build.workerman,
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
      l10n = intl.get_l10n('mail')
      notify_maintainers(
        repo, lilacinfo,
        l10n.format_value('package-staged-subject', {
          'pkg': pkgbase,
          'version': pkg_version,
        }),
        l10n.format_value('package-staged-body'),
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

def resolve_depends(repo: Optional[Repo], depends: Iterable[Dependency]) -> list[str]:
  need_build_first = set()
  depend_packages = []
  cwd = os.getcwd()

  for x in depends:
    p = x.resolve()
    if p is None:
      if repo is None or not repo.manages(x):
        # ignore depends that are not in repo
        continue
      need_build_first.add(x.pkgname)
    else:
      depend_packages.append(f'../{p.relative_to(cwd)}')

  if need_build_first:
    raise MissingDependencies(need_build_first)
  logger.info('depends: %s, resolved: %s', depends, depend_packages)

  return depend_packages

def may_need_cleanup() -> None:
  st = os.statvfs('/var/lib/archbuild')
  if st.f_bavail * st.f_bsize < 60 * 1024 ** 3:
    subprocess.check_call(['sudo', 'build-cleaner'])

def sign_and_copy(pkgdir: Path, dest: Path) -> None:
  pkgs = get_built_package_files(pkgdir)
  if not pkgs:
    logger.warning('no built packages found; package name and directory name mismatch?')

  for pkg in pkgs:
    subprocess.run([
      'gpg', '--pinentry-mode', 'loopback',
       '--passphrase', '', '--detach-sign', '--', pkg,
    ])
  for f in pkgs + [x.with_name(x.name + '.sig') for x in pkgs]:
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
  repo: Repo,
  lilacinfo: LilacInfo,
  pkgbase: str,
  pkgdir: Path,
  logfile: Path,
  depend_packages: list[str],
  update_info: NvResults,
  on_build_vers: OnBuildVers,
  commit_msg_template: str,
  bindmounts: list[str],
  tmpfs: list[str],
  deadline: float,
  packager: str,
  worker_no: int,
  workerman: WorkerManager,
) -> tuple[Optional[str], RUsage, Optional[Exception]]:
  '''
  return: package version, resource usage, error information
  '''
  input = {
    'depend_packages': depend_packages,
    'update_info': update_info.to_list(),
    'on_build_vers': on_build_vers,
    'commit_msg_template': commit_msg_template,
    'bindmounts': bindmounts,
    'tmpfs': tmpfs,
    'worker_no': worker_no,
    'workerman': workerman.name,
    'deadline': deadline,
    'reponame': repo.name,
  }
  fd, resultpath = tempfile.mkstemp(prefix=f'{pkgbase}-', suffix='.lilac')
  os.close(fd)
  input['result'] = resultpath
  input_bytes = json.dumps(input).encode()
  logger.debug('worker input: %r', input_bytes)

  cmd = workerman.get_worker_cmd(pkgbase)
  if systemd.available():
    _call_cmd = _call_cmd_systemd
  else:
    _call_cmd = _call_cmd_subprocess
  name = f'lilac-worker-{workerman.name}-{worker_no}'
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
    if report := r.get('report'):
      repo.send_error_report(
        lilacinfo,
        subject = report['subject'],
        msg = report['msg'],
        logfile = logfile,
      )
    error = BuildFailed(r['msg'])
  else:
    error = RuntimeError('unknown status from worker', st)

  version = r['version']
  if ru2 := r.get('rusage'):
    rusage = RUsage(*ru2)
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

