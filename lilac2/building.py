import os
import logging
import subprocess
from pathlib import Path
from typing import Optional, Iterable, List, Set, TYPE_CHECKING
from types import SimpleNamespace

from . import pkgbuild
from .typing import LilacMod, Cmd
from .cmd import run_cmd
from .packages import Dependency
from .nvchecker import NvResults

if TYPE_CHECKING:
  from .repo import Repo
  assert Repo # make pyflakes happy
  del Repo

logger = logging.getLogger(__name__)

build_output: Optional[str] = None

class MissingDependencies(Exception):
  def __init__(self, pkgs: Set[str]) -> None:
    self.deps = pkgs

class SkipBuild(Exception):
  def __init__(self, msg: str) -> None:
    self.msg = msg

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

  global build_output
  # reset in case no one cleans it up
  build_output = None

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

    run_cmd(["sh", "-c", "rm -f -- *.pkg.tar.xz *.pkg.tar.xz.sig *.src.tar.gz"])
    pre_build = getattr(mod, 'pre_build', None)
    if pre_build is not None:
      logger.debug('accept_noupdate=%r, oldver=%r, newver=%r', accept_noupdate, oldver, newver)
      pre_build()
    pkgbuild.check_srcinfo()
    run_cmd(['recv_gpg_keys'])

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

    makepkg_args: List[str] = []
    if hasattr(mod, 'makepkg_args'):
        makepkg_args = mod.makepkg_args

    call_build_cmd(
      build_prefix, depend_packages, bindmounts, build_args, makechrootpkg_args, makepkg_args)
    pkgs = [x for x in os.listdir() if x.endswith('.pkg.tar.xz')]
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
  global build_output
  cmd: Cmd
  if build_prefix == 'makepkg':
    cmd = ['makepkg', '--holdver']
  else:
    cmd = ['%s-build' % build_prefix]
    cmd.extend(build_args)
    cmd.append('--')

    if depends:
      for x in depends:
        cmd += ['-I', x]

    for b in bindmounts:
      # Skipping non-existent source paths
      # See --bind in systemd-nspawn(1) for bindmount spec details
      # Note that this check does not consider all possible formats
      source_dir = b.split(':')[0]
      if not os.path.exists(source_dir):
        logger.warning('Invalid bindmount spec %s: '
                       'source dir does not exist', b)
        continue
      cmd += ['-d', b]

    cmd.extend(makechrootpkg_args)
    cmd.extend(['--'])
    cmd.extend(makepkg_args)
    cmd.extend(['--holdver'])

  # NOTE that Ctrl-C here may not succeed
  try:
    build_output = run_cmd(cmd, use_pty=True)
  except subprocess.CalledProcessError:
    build_output = None
    raise

