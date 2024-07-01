from __future__ import annotations

import os
import logging
import subprocess
from typing import Optional, List, Generator, Union
from types import SimpleNamespace
import contextlib
import json
import sys
from pathlib import Path
import platform

import pyalpm

from .vendor.nicelogger import enable_pretty_logging
from .vendor.myutils import file_lock

from . import pkgbuild
from .typing import LilacMod, LilacInfo, Cmd
from .cmd import run_cmd, UNTRUSTED_PREFIX
from .api import (
  vcs_update, get_pkgver_and_pkgrel, update_pkgrel,
  _next_pkgrel,
)
from .nvchecker import NvResults
from .tools import kill_child_processes
from .lilacpy import load_lilac
from .lilacyaml import load_lilacinfo
from .const import _G, PACMAN_DB_DIR, mydir
from .repo import Repo

logger = logging.getLogger(__name__)

class SkipBuild(Exception):
  def __init__(self, msg: str) -> None:
    self.msg = msg

@contextlib.contextmanager
def may_update_pkgrel() -> Generator[None, None, None]:
  pkgver, pkgrel = get_pkgver_and_pkgrel()
  yield

  if pkgver is None or pkgrel is None:
    return

  pkgver2, pkgrel2 = get_pkgver_and_pkgrel()
  if pkgver2 is None or pkgrel2 is None:
    return

  if pkgver == pkgver2 and \
     pyalpm.vercmp(f'1-{pkgrel}', f'1-{pkgrel2}') >= 0:
    try:
      update_pkgrel(_next_pkgrel(pkgrel))
    except ValueError:
      # pkgrel is not a number, resetting to 1
      update_pkgrel(1)

def lilac_build(
  worker_no: int,
  mod: LilacMod,
  depend_packages: list[str] = [],
  build_prefix: Optional[str] = None,
  update_info: NvResults = NvResults(),
  bindmounts: list[str] = [],
  tmpfs: list[str] = [],
) -> None:
  success = False
  _G.built_version = None

  try:
    oldver = update_info.oldver
    newver = update_info.newver

    if not hasattr(mod, '_G'):
      # fill nvchecker result unless already filled (e.g. by hand)
      mod._G = SimpleNamespace(
        oldver = oldver,
        newver = newver,
        oldvers = [x.oldver for x in update_info],
        newvers = [x.newver for x in update_info],
      )

    prepare = getattr(mod, 'prepare', None)
    if prepare is not None:
      msg = prepare()
      if isinstance(msg, str):
        raise SkipBuild(msg)

    run_cmd(["sh", "-c", "rm -f -- *.pkg.tar.xz *.pkg.tar.xz.sig *.pkg.tar.zst *.pkg.tar.zst.sig"])
    pre_build = getattr(mod, 'pre_build', None)

    with may_update_pkgrel():
      if pre_build is not None:
        logger.debug('oldver=%r, newver=%r', oldver, newver)
        pre_build()
      run_cmd(['recv_gpg_keys'])
      vcs_update()

    pkgvers = pkgbuild.check_srcinfo()
    _G.built_version = str(pkgvers)

    default_build_prefix = 'extra-%s' % (platform.machine() or 'x86_64')
    build_prefix = build_prefix or getattr(
      mod, 'build_prefix', default_build_prefix)
    if not isinstance(build_prefix, str):
      raise TypeError('build_prefix', build_prefix)

    build_args: List[str] = []
    if hasattr(mod, 'build_args'):
      build_args = mod.build_args

    makechrootpkg_args = ['-l', f'lilac-{worker_no}']
    if hasattr(mod, 'makechrootpkg_args'):
      makechrootpkg_args.extend(mod.makechrootpkg_args)

    makepkg_args = ['--noprogressbar']
    if hasattr(mod, 'makepkg_args'):
      makepkg_args.extend(mod.makepkg_args)

    call_build_cmd(
      build_prefix, depend_packages, bindmounts, tmpfs,
      build_args, makechrootpkg_args, makepkg_args,
    )

    pkgs = [x for x in os.listdir() if x.endswith(('.pkg.tar.xz', '.pkg.tar.zst'))]
    if not pkgs:
      raise Exception('no package built')
    post_build = getattr(mod, 'post_build', None)
    if post_build is not None:
      with file_lock(mydir / 'post_build.lock'):
        post_build()
    success = True

  finally:
    post_build_always = getattr(mod, 'post_build_always', None)
    if post_build_always is not None:
      post_build_always(success=success)

def call_build_cmd(
  build_prefix: str, depends: List[str],
  bindmounts: list[str] = [],
  tmpfs: list[str] = [],
  build_args: list[str] = [],
  makechrootpkg_args: List[str] = [],
  makepkg_args: List[str] = [],
) -> None:
  cmd: Cmd
  if build_prefix == 'makepkg':
    pwd = os.getcwd()
    basename = os.path.basename(pwd)
    extra_args = ['--share-net', '--bind', pwd, f'/tmp/{basename}', '--chdir', f'/tmp/{basename}']
    cmd = UNTRUSTED_PREFIX + extra_args + ['makepkg', '--holdver'] # type: ignore
  else:
    gpghome = os.path.expanduser('~/.lilac/gnupg')
    cmd = ['env', f'GNUPGHOME={gpghome}', '%s-build' % build_prefix]
    cmd.extend(build_args)
    cmd.append('--')

    for x in depends:
      cmd += ['-I', x]

    for b in bindmounts:
      # need to make sure source paths exist
      # See --bind in systemd-nspawn(1) for bindmount spec details
      # Note that this check does not consider all possible formats
      source_dir = b.split(':')[0]
      if not os.path.exists(source_dir):
        os.makedirs(source_dir)
      cmd += ['-d', b]

    for t in tmpfs:
      cmd += ['-t', t]

    cmd.extend(makechrootpkg_args)
    cmd.extend(['--'])
    cmd.extend(makepkg_args)
    cmd.extend(['--holdver'])

  # NOTE that Ctrl-C here may not succeed
  run_build_cmd(cmd)

def run_build_cmd(cmd: Cmd) -> None:
  logger.info('Running build command: %r', cmd)

  p = subprocess.Popen(
    cmd,
    stdin = subprocess.DEVNULL,
  )

  while True:
    try:
      code = p.wait(10)
    except subprocess.TimeoutExpired:
      st = os.stat(1)
      if st.st_size > 1024 ** 3: # larger than 1G
        kill_child_processes()
        logger.error('\n\nOutput is quite long and killed.')
    else:
      if code != 0:
        raise subprocess.CalledProcessError(code, cmd)
      break

def main() -> None:
  enable_pretty_logging('DEBUG')

  from .tools import read_config
  config = read_config()
  repo = _G.repo = Repo(config)
  pkgbuild.load_data(PACMAN_DB_DIR)
  _G.commit_msg_prefix = repo.commit_msg_prefix

  input = json.load(sys.stdin)
  logger.debug('got input: %r', input)
  try:
    with load_lilac(Path('.')) as mod:
      _G.mod = mod
      lilac_build(
        worker_no = input['worker_no'],
        mod = mod,
        depend_packages = input['depend_packages'],
        update_info = NvResults.from_list(input['update_info']),
        bindmounts = input['bindmounts'],
        tmpfs = input['tmpfs'],
      )
    r = {'status': 'done'}
  except SkipBuild as e:
    r = {
      'status': 'skipped',
      'msg': e.msg,
    }
  except Exception as e:
    r = {
      'status': 'failed',
      'msg': repr(e),
    }
    sys.stdout.flush()
    try:
      handle_failure(e, repo, mod, Path(input['logfile']))
    except UnboundLocalError:
      # mod failed to load
      info = load_lilacinfo(Path('.'))
      handle_failure(e, repo, info, Path(input['logfile']))
  except KeyboardInterrupt:
    logger.info('KeyboardInterrupt received')
    r = {
      'status': 'failed',
      'msg': 'KeyboardInterrupt',
    }
  finally:
    # say goodbye to all our children
    kill_child_processes()

  r['version'] = getattr(_G, 'built_version', None) # type: ignore

  with open(input['result'], 'w') as f:
    json.dump(r, f)

def handle_failure(
  e: Exception, repo: Repo, mod: Union[LilacMod, LilacInfo], logfile: Path,
) -> None:
  logger.error('build failed', exc_info=e)

  if isinstance(e, pkgbuild.ConflictWithOfficialError):
    reason = ''
    if e.groups:
      reason += f'Package is added to officail repository: {e.groups}\n'
    if e.packages:
      reason += f'Package will replace package in offical repository: {e.packages}\n'
    repo.send_error_report(
      mod, subject='%s is conflicted with offical repository', msg = reason,
    )

  elif isinstance(e, pkgbuild.DowngradingError):
    repo.send_error_report(
      mod, subject='%s is older than packaged version in this repository',
      msg=f'Current packaging version of package {e.pkgname} is {e.built_version}, however, already newer version {e.repo_version} in repository\n',
    )

  else:
    repo.send_error_report(mod, exc=e, logfile=logfile)

if __name__ == '__main__':
  main()
