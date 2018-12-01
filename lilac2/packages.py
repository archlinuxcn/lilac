from collections import defaultdict, namedtuple
from pathlib import Path
from typing import Dict, Union, Tuple, Set, Optional

import archpkg

from .api import run_cmd
from .typing import LilacMods

def get_dependency_map(
  depman: 'DependencyManager', mods: LilacMods,
) -> Dict[str, Set['Dependency']]:
  map: Dict[str, Set['Dependency']] = defaultdict(set)
  rmap: Dict[str, Set[str]] = defaultdict(set)

  for name, mod in mods.items():
    depends = getattr(mod, 'depends', ())

    ds = [depman.get(d) for d in depends]
    for d in ds:
      rmap[d.pkgname].add(name)
    map[name].update(ds)

  for name, deps in map.items():
    dependers = rmap[name]
    for dd in dependers:
      map[dd].update(deps)

  return map

_DependencyTuple = namedtuple(
  '_DependencyTuple', 'pkgdir pkgname')

class Dependency(_DependencyTuple):
  def resolve(self) -> Optional[Path]:
    try:
      return self._find_local_package()
    except FileNotFoundError:
      return None

  def managed(self) -> bool:
    return (self.pkgdir / 'lilac.py').exists()

  def _find_local_package(self) -> Path:
    files = [x for x in self.pkgdir.iterdir()
             if x.name.endswith('.pkg.tar.xz')]
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

  def get(self, what: Union[str, Tuple[str, str]]) -> Dependency:
    if isinstance(what, tuple):
      pkgbase, pkgname = what
    else:
      pkgbase = pkgname = what

    if pkgname not in self._CACHE:
      self._CACHE[pkgname] = Dependency(
        self.repodir / pkgbase, pkgname)
    return self._CACHE[pkgname]

def get_changed_packages(revisions: str) -> Set[str]:
  cmd = ["git", "diff", "--name-only", revisions]
  r = run_cmd(cmd).splitlines()
  ret = {x.split('/', 1)[0] for x in r}
  return ret

