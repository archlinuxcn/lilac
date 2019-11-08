from __future__ import annotations

# PKGBUILD related stuff that lilac uses (excluding APIs)

import os
import subprocess
from typing import Dict, List, Optional, Set, Tuple

import pyalpm

from .const import _G

_official_repos = ['core', 'extra', 'community', 'multilib']
_official_packages: Set[str] = set()
_official_groups: Set[str] = set()
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

def init_data(dbpath: os.PathLike, *, quiet: bool = False) -> None:
  global _repo_package_versions

  if quiet:
    kwargs = {'stdout': subprocess.DEVNULL}
  else:
    kwargs = {}

  for _ in range(3):
    p = subprocess.run( # type: ignore # what a mess...
      ['fakeroot', 'pacman', '-Sy', '--dbpath', dbpath],
      **kwargs,
    )
    if p.returncode == 0:
      break
  else:
    p.check_returncode()

  H = pyalpm.Handle('/', str(dbpath))
  for repo in _official_repos:
    db = H.register_syncdb(repo, 0)
    _official_packages.update(p.name for p in db.pkgcache)
    _official_groups.update(g[0] for g in db.grpcache)

  if hasattr(_G, 'repo'):
    db = H.register_syncdb(_G.repo.name, 0)
    _repo_package_versions = {p.name: p.version for p in db.pkgcache}

def get_official_packages() -> Set[str]:
  return _official_packages

def check_srcinfo() -> None:
  srcinfo = get_srcinfo()
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

  _G.epoch, _G.pkgver, _G.pkgrel = _get_package_version(srcinfo)

  # check if the newly built package is older than the existing
  # package in repos or not
  built_version = format_package_version(_G.epoch, _G.pkgver, _G.pkgrel)
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

def get_srcinfo() -> List[str]:
  out = subprocess.check_output(
    ['makepkg', '--printsrcinfo'],
    universal_newlines = True,
  )
  return out.splitlines()

def _get_package_version(srcinfo: List[str]) -> Tuple[Optional[str], str, str]:
  epoch = pkgver = pkgrel = None

  for line in get_srcinfo():
    line = line.strip()
    if not epoch and line.startswith('epoch = '):
      epoch = line.split()[-1]
    elif not pkgver and line.startswith('pkgver = '):
      pkgver = line.split()[-1]
    elif not pkgrel and line.startswith('pkgrel = '):
      pkgrel = line.split()[-1]

  assert pkgver is not None
  assert pkgrel is not None
  return epoch, pkgver, pkgrel

def format_package_version(epoch: Optional[str], pkgver: str, pkgrel: str) -> str:
  if epoch:
    return '{}:{}-{}'.format(epoch, pkgver, pkgrel)
  else:
    return '{}-{}'.format(pkgver, pkgrel)
