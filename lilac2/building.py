from __future__ import annotations

import os
import logging
import subprocess
from pathlib import Path
from typing import (
  Optional, Iterable, List, Set, TYPE_CHECKING,
  Generator,
)
from types import SimpleNamespace
import contextlib

import pyalpm

from . import pkgbuild
from .typing import LilacMod, Cmd
from .cmd import run_cmd, UNTRUSTED_PREFIX
from .api import (
  vcs_update, get_pkgver_and_pkgrel, update_pkgrel,
  _next_pkgrel,
)
from .packages import Dependency
from .nvchecker import NvResults
from .tools import kill_child_processes

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
    update_pkgrel(_next_pkgrel(pkgrel))

def lilac_build(
  mod: LilacMod,
  repo: Optional['Repo'],
  build_prefix: Optional[str] = None,
  update_info: NvResults = NvResults(),
  accept_noupdate: bool = False,
  depends: Iterable[Dependency] = (),
  bindmounts: List[str] = [],
) -> None:
  success = False

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
        logger.debug('accept_noupdate=%r, oldver=%r, newver=%r', accept_noupdate, oldver, newver)
        pre_build()
      run_cmd(['recv_gpg_keys'])
      vcs_update()

    pkgbuild.check_srcinfo()

    need_build_first = set()
    build_prefix = build_prefix or getattr(
      mod, 'build_prefix', 'extra-x86_64')
    depend_packages = []

    for x in depends:
      p = x.resolve()
      if p is None:
        if repo is None or not repo.manages(x):
          # ignore depends that are not in repo
          continue
        need_build_first.add(x.pkgname)
      else:
        depend_packages.append(p)

    if need_build_first:
      raise MissingDependencies(need_build_first)
    logger.info('depends: %s, resolved: %s', depends, depend_packages)

    build_args: List[str] = []
    if hasattr(mod, 'build_args'):
        build_args = mod.build_args

    makechrootpkg_args: List[str] = []
    if hasattr(mod, 'makechrootpkg_args'):
        makechrootpkg_args = mod.makechrootpkg_args

    makepkg_args = ['--noprogressbar']
    if hasattr(mod, 'makepkg_args'):
        makepkg_args.extend(mod.makepkg_args)

    call_build_cmd(
      build_prefix, depend_packages, bindmounts,
      build_args, makechrootpkg_args, makepkg_args,
    )

    pkgs = [x for x in os.listdir() if x.endswith(('.pkg.tar.xz', '.pkg.tar.zst'))]
    if not pkgs:
      raise Exception('no package built')
    post_build = getattr(mod, 'post_build', None)
    if post_build is not None:
      post_build()
    success = True
  finally:
    post_build_always = getattr(mod, 'post_build_always', None)
    if post_build_always is not None:
      post_build_always(success=success)

def call_build_cmd(
  build_prefix: str, depends: List[Path],
  bindmounts: List[str] = [],
  build_args: List[str] = [],
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
    cmd = ['%s-build' % build_prefix]
    cmd.extend(build_args)
    cmd.append('--')

    if depends:
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

    cmd.extend(makechrootpkg_args)
    cmd.extend(['--'])
    cmd.extend(makepkg_args)
    cmd.extend(['--holdver'])

  # NOTE that Ctrl-C here may not succeed
  try:
    run_build_cmd(cmd)
  finally:
    may_need_cleanup()

def run_build_cmd(cmd: Cmd) -> None:
  logger.info('Running build command: %r', cmd)

  p = subprocess.Popen(
    cmd,
    stdin = subprocess.DEVNULL,
  )

  try:
    while True:
      try:
        code = p.wait(10)
      except subprocess.TimeoutExpired:
        st = os.stat(1)
        if st.st_size > 1024 ** 3: # larger than 1G
          kill_child_processes()
          logger.error('\n\n输出过多，已击杀。')
      else:
        if code != 0:
          raise subprocess.CalledProcessError(code, cmd)
        break
  finally:
    # say goodbye to all our children
    kill_child_processes()

def may_need_cleanup() -> None:
  st = os.statvfs('/var/lib/archbuild')
  if st.f_bavail * st.f_bsize < 60 * 1024 ** 3:
    subprocess.check_call(['sudo', 'build-cleaner'])
