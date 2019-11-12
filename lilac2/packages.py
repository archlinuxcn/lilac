from __future__ import annotations

from collections import defaultdict, namedtuple
from pathlib import Path
from typing import Dict, Union, Tuple, Set, Optional
import re

from toposort import toposort_flatten

import archpkg

from .api import run_cmd
from .typing import LilacMods

def get_dependency_map(
  depman: DependencyManager, mods: LilacMods,
) -> Dict[str, Set[Dependency]]:
  """

  :param depman: a DependencyManager instance
  :param mods: the list of modules to be built by lilac
  :return:
  """
  map: Dict[str, Set[Dependency]] = defaultdict(set)
  shallow_map: Dict[str, Set[str]] = defaultdict(set)
  rmap: Dict[str, Set[str]] = defaultdict(set)

  for name, mod in mods.items():
    depends = getattr(mod, 'repo_depends', ())

    ds = [depman.get(d) for d in depends]
    if ds:
      for d in ds:
        shallow_map[name].add(d.pkgname)
        rmap[d.pkgname].add(name)
      map[name].update(ds)

  dep_order = toposort_flatten(shallow_map)
  for name in dep_order:
    if name in rmap:
      deps = map[name]
      dependers = rmap[name]
      for dd in dependers:
        map[dd].update(deps)

  return map

_DependencyTuple = namedtuple(
  '_DependencyTuple', 'pkgdir pkgname')

class Dependency(_DependencyTuple):
  """
  Dependency object resembles a package
  """
  def resolve(self) -> Optional[Path]:
    """
    resolves the location to the local package, returns None if fails
    :return: the path to the local package or none
    """
    try:
      return self._find_local_package()
    except FileNotFoundError:
      return None

  def _find_local_package(self) -> Path:
    """
    finds the newest local package for this dependency
    :return: the path to the local package
    """
    files = [x for x in self.pkgdir.iterdir()
             if x.name.endswith(('.pkg.tar.xz', '.pkg.tar.zst'))]
    pkgs = []
    for x in files:
      info = archpkg.PkgNameInfo.parseFilename(x.name)
      if info.name == self.pkgname:
        pkgs.append(x)

    if len(pkgs) == 1:
      return pkgs[0]
    elif not pkgs:
      raise FileNotFoundError
    else:
      ret = sorted(
        pkgs, reverse=True, key=lambda x: x.stat().st_mtime)[0]
      return ret

class DependencyManager:
  _CACHE: Dict[str, Dependency] = {}

  def __init__(self, repodir: Path) -> None:
    self.repodir = repodir
    """ the dir to git repo """

  def get(self, what: Union[str, Tuple[str, str]]) -> Dependency:
    """
    Gets a package as a Dependency object
    :param what: either a tuple (package base dir name, package name)
    or just the name (if package base dir name is the same as package name)
    :return: Dependency object of that package
    """
    if isinstance(what, tuple):
      pkgbase, pkgname = what
    else:
      pkgbase = pkgname = what

    if pkgname not in self._CACHE:
      self._CACHE[pkgname] = Dependency(
        self.repodir / pkgbase, pkgname)
    return self._CACHE[pkgname]

def get_changed_packages(from_: str, to: str) -> Set[str]:
  """
  gets the changed packages between 2 git commits
  :param from_: older commit
  :param to: newer commit
  :return: changed packages
  """
  cmd = ["git", "diff", "--name-only", '--relative', from_, to]
  r = run_cmd(cmd).splitlines()
  ret = {x.split('/', 1)[0] for x in r}
  return ret

_re_package = re.compile(r'package(?:_(.+))?\s*\(')

def get_all_managed_packages(repodir: Path) -> Set[Tuple[str, str]]:
  packages: Set[Tuple[str, str]] = set()
  for pkg in repodir.glob('*/PKGBUILD'):
    pkgbase = pkg.parent.name

    pkgfile = pkg.with_name('package.list')
    if pkgfile.exists():
      with open(pkgfile) as f:
        packages.update((pkgbase, x) for x in f.read().split())
        continue

    found = False
    with open(pkg) as f:
      for l in f:
        l = l.strip()
        m = _re_package.match(l)
        if m:
          found = True
          if m.group(1):
            packages.add((pkgbase, m.group(1)))
          else:
            packages.add((pkgbase, pkgbase))
    if not found:
      packages.add((pkgbase, pkgbase))

  return packages

