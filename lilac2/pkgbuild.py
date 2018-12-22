# PKGBUILD related stuff that lilac uses (excluding APIs)

import os
import subprocess
from typing import List, Set, Tuple

import archpkg
import pyalpm

from .const import _G

_official_repos = ['core', 'extra', 'community', 'multilib']
_official_packages: Set[str] = set()
_official_groups: Set[str] = set()

class ConflictWithOfficialError(Exception):
  def __init__(self, groups, packages):
    self.groups = groups
    self.packages = packages

class OlderThanRepoPackage(Exception):
  def __init__(self, pkgname, built_version, repo_version):
    self.pkgname = pkgname
    self.built_version = built_version
    self.repo_version = repo_version

def init_data(dbpath: os.PathLike) -> None:
  for _ in range(3):
    p = subprocess.run(
      ['fakeroot', 'pacman', '-Sy', '--dbpath', dbpath],
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
  built_version = format_package_version()
  for pkgname in pkgnames:
    try:
      pkg_info = archpkg.get_package_info(pkgname)
      repo_version = pkg_info['Version']
      if pyalpm.vercmp(built_version, repo_version) < 0:
        raise OlderThanRepoPackage(pkgname, built_version, repo_version)
    except subprocess.CalledProcessError:
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

def _get_package_version(srcinfo: List[str]) -> Tuple[str, str]:
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

def format_package_version() -> str:
  if _G.epoch:
    return '{}:{}-{}'.format(_G.epoch, _G.pkgver, _G.pkgrel)
  else:
    return '{}-{}'.format(_G.pkgver, _G.pkgrel)
