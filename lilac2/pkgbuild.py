from __future__ import annotations

# PKGBUILD related stuff that lilac uses (excluding APIs)

import os
import time
import subprocess
from typing import Dict, List, Optional, Union
from pathlib import Path
from contextlib import suppress

import pyalpm

from .vendor.myutils import safe_overwrite

from .const import _G, OFFICIAL_REPOS
from .cmd import UNTRUSTED_PREFIX
from .typing import PkgVers

_official_packages: Dict[str, int] = {}
_official_groups: Dict[str, int] = {}
_repo_package_versions: Dict[str, str] = {}

class ConflictWithOfficialError(Exception):
  def __init__(self, groups, packages):
    self.groups = groups
    self.packages = packages

class DowngradingError(Exception):
  def __init__(self, pkgname, built_version, repo_version):
    self.pkgname = pkgname
    self.built_version = built_version
    self.repo_version = repo_version

def _load_timed_dict(
  path: os.PathLike, deadline: int,
) -> Dict[str, int]:
  data = {}
  with suppress(FileNotFoundError), open(path) as f:
    for line in f:
      name, t_str = line.split(None, 1)
      t = int(t_str)
      if t >= deadline:
        data[name] = t

  return data

def _save_timed_dict(
  path: os.PathLike, data: Dict[str, int],
) -> None:
  data_str = ''.join(f'{k} {v}\n' for k, v in data.items())
  safe_overwrite(str(path), data_str, mode='w')

def update_pacmandb(dbpath: Path, pacman_conf: Optional[str],
                    *, quiet: bool = False) -> None:
  stdout = subprocess.DEVNULL if quiet else None

  for update_arg in ['-Sy', '-Fy']:

    cmd: List[Union[str, Path]] = [
      'fakeroot', 'pacman', update_arg, '--dbpath', dbpath,
    ]
    if pacman_conf is not None:
      cmd += ['--config', pacman_conf]

    for _ in range(3):
      p = subprocess.run(cmd, stdout = stdout)
      if p.returncode == 0:
        break
    else:
      p.check_returncode()

def update_data(dbpath: Path, pacman_conf: Optional[str],
                *, quiet: bool = False) -> None:
  update_pacmandb(dbpath, pacman_conf, quiet=quiet)

  now = int(time.time())
  deadline = now - 90 * 86400
  pkgs = _load_timed_dict(dbpath / 'packages.txt', deadline)
  groups = _load_timed_dict(dbpath / 'groups.txt', deadline)

  H = pyalpm.Handle('/', str(dbpath))
  for repo in OFFICIAL_REPOS:
    db = H.register_syncdb(repo, 0)
    pkgs.update((p.name, now) for p in db.pkgcache)
    groups.update((g[0], now) for g in db.grpcache)

  _save_timed_dict(dbpath / 'packages.txt', pkgs)
  _save_timed_dict(dbpath / 'groups.txt', groups)

def load_data(dbpath: Path) -> None:
  global _repo_package_versions

  now = int(time.time())
  deadline = now - 90 * 86400
  _official_packages.update(
    _load_timed_dict(dbpath / 'packages.txt', deadline))
  _official_groups.update(
    _load_timed_dict(dbpath / 'groups.txt', deadline))

  if hasattr(_G, 'repo'):
    H = pyalpm.Handle('/', str(dbpath))
    db = H.register_syncdb(_G.repo.name, 0)
    _repo_package_versions = {p.name: p.version for p in db.pkgcache}

def check_srcinfo() -> PkgVers:
  srcinfo = get_srcinfo().decode('utf-8').splitlines()
  bad_groups = []
  bad_packages = []
  pkgnames = []

  for line in srcinfo:
    line = line.strip()
    if line.startswith('groups = '):
      g = line.split()[-1]
      if g in _official_groups:
        bad_groups.append(g)
    elif line.startswith('replaces = '):
      pkg = line.split()[-1]
      if pkg in _official_packages:
        bad_packages.append(pkg)
    elif line.startswith('pkgname = '):
      pkgnames.append(line.split()[-1])

  pkgvers = _get_package_version(srcinfo)

  # check if the newly built package is older than the existing
  # package in repos or not
  built_version = str(pkgvers)
  for pkgname in pkgnames:
    try:
      repo_version = _repo_package_versions[pkgname]
      if pyalpm.vercmp(built_version, repo_version) < 0:
        raise DowngradingError(pkgname, built_version, repo_version)
    except KeyError:
      # the newly built package is not in repos yet - fine
      pass

  if bad_groups or bad_packages:
    raise ConflictWithOfficialError(bad_groups, bad_packages)

  return pkgvers

def get_srcinfo() -> bytes:
  pwd = os.getcwd()
  basename = os.path.basename(pwd)
  # makepkg wants *.install file and write permissions to simply print out info :-(
  extra_binds = ['--bind', pwd, f'/tmp/{basename}', '--chdir', f'/tmp/{basename}']
  out = subprocess.check_output(
    UNTRUSTED_PREFIX + extra_binds + ['makepkg', '--printsrcinfo'], # type: ignore
  )
  return out

def _get_package_version(srcinfo: List[str]) -> PkgVers:
  epoch = pkgver = pkgrel = None

  for line in srcinfo:
    line = line.strip()
    if not epoch and line.startswith('epoch = '):
      epoch = line.split()[-1]
    elif not pkgver and line.startswith('pkgver = '):
      pkgver = line.split()[-1]
    elif not pkgrel and line.startswith('pkgrel = '):
      pkgrel = line.split()[-1]

  assert pkgver is not None
  assert pkgrel is not None
  return PkgVers(epoch, pkgver, pkgrel)
