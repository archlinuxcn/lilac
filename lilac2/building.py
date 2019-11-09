from __future__ import annotations

import os
import logging
import subprocess
from pathlib import Path
from typing import (
  Optional, Iterable, List, Set, TYPE_CHECKING,
  BinaryIO, cast,
)
from types import SimpleNamespace, FrameType
import signal

from . import pkgbuild
from .typing import LilacMod, Cmd
from .cmd import run_cmd
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

def lilac_build(
  mod: LilacMod,
  repo: Optional['Repo'],
  logfile: Path,
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

    run_cmd(["sh", "-c", "rm -f -- *.pkg.tar.xz *.pkg.tar.xz.sig *.pkg.tar.zst *.pkg.tar.zst.sig *.src.tar.gz"])
    pre_build = getattr(mod, 'pre_build', None)
    if pre_build is not None:
      logger.debug('accept_noupdate=%r, oldver=%r, newver=%r', accept_noupdate, oldver, newver)
      pre_build()
    with logfile.open('wb') as f:
      pkgbuild.check_srcinfo(cast(BinaryIO, f))
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

    with logfile.open('wb') as f:
      call_build_cmd(
        build_prefix, depend_packages, cast(BinaryIO, f),
        bindmounts,
        build_args, makechrootpkg_args, makepkg_args)

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
  logfile: BinaryIO,
  bindmounts: List[str] = [],
  build_args: List[str] = [],
  makechrootpkg_args: List[str] = [],
  makepkg_args: List[str] = [],
) -> None:
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
  run_build_cmd(cmd, logfile)

def run_build_cmd(cmd: Cmd, logfile: BinaryIO) -> None:
  p = subprocess.Popen(
    cmd,
    # stdin = subprocess.DEVNULL,
    stdout = logfile,
    stderr = subprocess.STDOUT,
  )
  code = -1
  exited = False

  def wakeup(signum: int, sigframe: FrameType) -> None:
    pass

  signal.signal(signal.SIGCHLD, wakeup)
  signal.signal(signal.SIGALRM, wakeup)
  signal.setitimer(signal.ITIMER_REAL, 10, 10)

  try:
    while True:
      try:
        signal.pause()

        while True:
          st = os.waitid(
            os.P_ALL, 0, os.WEXITED | os.WNOHANG)
          if st is None:
            break
          if st.si_pid == p.pid:
            code = st.si_status
            kill_child_processes()
            exited = True
      except ChildProcessError:
        # no more children
        break
      else:
        if exited and code != 0:
          raise subprocess.CalledProcessError(code, cmd)

        if not exited:
          st = os.stat(logfile.fileno())
          if st.st_size > 1024 ** 3: # larger than 1G
            kill_child_processes()
            logfile.write(
              '\n\n输出过多，已击杀。\n'.encode('utf-8'))
  finally:
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, 0, 0)
    # say goodbye to all our children
    kill_child_processes()
