from __future__ import annotations

# PKGBUILD related stuff that lilac uses (excluding APIs)

import os
import subprocess
from typing import (
  Dict, List, Optional, Set, Tuple,
)

import pyalpm

from .const import _G

_official_repos = ['core', 'extra', 'community', 'multilib']
""" Archlinux official repos """
_official_packages: Set[str] = set()
""" packages in official repos """
_official_groups: Set[str] = set()
""" groups in official repos """
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
  """
  loads the versions and names of installed packages from pacman database
  into _repo_package_versions
  :param dbpath: path to pacman database
  :param quiet: whether redirect stdout to /dev/null
  :return:
  """
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
  """
  gets a list of packages in Archlinux official repos
  :return:
  """
  return _official_packages

def check_srcinfo() -> None:
  """
  checks if the PKGBUILD script is well defined (not conflicting with official repo)
  :raises DowngradingException: There is a newer version of this package installed
  :raises ConflictWithOfficialError: The PKGBUILD conflicts with either groups or packages in the official repo
  :return:
  """
  srcinfo = get_srcinfo()
  bad_groups = []    # list of conflicting group names
  bad_packages = []  # list of conflicting package names
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
  """
  gets .SRCINFO of a PKGBUILD script using makepkg
  :return: .SRCINFO, split into list of string
  """
  out = subprocess.check_output(
    ['makepkg', '--printsrcinfo'],
  )
  return out.decode('utf-8').splitlines()

def _get_package_version(srcinfo: List[str]) -> Tuple[Optional[str], str, str]:
  """
  gets the version of a PKGBUILD script from .SRCINFO
  :param srcinfo: .SRCINFO, split into list of string
  :return: tuple (epoch, pkgver, pkgrel), epoch might be None
  """
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
  return epoch, pkgver, pkgrel

def format_package_version(epoch: Optional[str], pkgver: str, pkgrel: str) -> str:
  if epoch:
    return '{}:{}-{}'.format(epoch, pkgver, pkgrel)
  else:
    return '{}-{}'.format(pkgver, pkgrel)
