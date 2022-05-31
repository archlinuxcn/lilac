from __future__ import annotations

from collections import defaultdict, namedtuple
from pathlib import Path
from typing import Dict, Union, Tuple, Set, Optional
import re
import graphlib

from .vendor import archpkg

from .api import run_cmd
from .typing import LilacInfos
from . import lilacyaml

def get_dependency_map(
  depman: DependencyManager, lilacinfos: LilacInfos,
) -> Dict[str, Set[Dependency]]:
  '''compute ordered, complete dependency relations between pkgbases (the directory names)

  This function does not make use of pkgname because they maybe the same for
  different pkgdir. Those are carried by Dependency and used elsewhere.
  '''
  map: Dict[str, Set[Dependency]] = defaultdict(set)
  pkgdir_map: Dict[str, Set[str]] = defaultdict(set)
  rmap: Dict[str, Set[str]] = defaultdict(set)

  for pkgbase, info in lilacinfos.items():
    depends = info.repo_depends

    ds = [depman.get(d) for d in depends]
    if ds:
      for d in ds:
        pkgdir_map[pkgbase].add(d.pkgdir.name)
        rmap[d.pkgdir.name].add(pkgbase)
      map[pkgbase].update(ds)

  dep_order = graphlib.TopologicalSorter(pkgdir_map).static_order()
  for pkgbase in dep_order:
    if pkgbase in rmap:
      deps = map[pkgbase]
      dependers = rmap[pkgbase]
      for dd in dependers:
        map[dd].update(deps)

  return map

_DependencyTuple = namedtuple(
  '_DependencyTuple', 'pkgdir pkgname')

class Dependency(_DependencyTuple):
  pkgdir: Path
  pkgname: str

  def resolve(self) -> Optional[Path]:
    try:
      files = [x for x in self.pkgdir.iterdir()
              if x.name.endswith(('.pkg.tar.xz', '.pkg.tar.zst'))]
    except FileNotFoundError:
      return None

    pkgs = []
    for x in files:
      info = archpkg.PkgNameInfo.parseFilename(x.name)
      if info.name == self.pkgname:
        pkgs.append(x)

    if len(pkgs) == 1:
      return pkgs[0]
    elif not pkgs:
      return None
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

    key = '/'.join((pkgbase, pkgname))
    if key not in self._CACHE:
      self._CACHE[key] = Dependency(
        self.repodir / pkgbase, pkgname)
    return self._CACHE[key]

def get_changed_packages(from_: str, to: str) -> Set[str]:
  cmd = ["git", "diff", "--name-only", '--relative', from_, to]
  r = run_cmd(cmd).splitlines()
  ret = {x.split('/', 1)[0] for x in r}
  return ret

_re_package = re.compile(r'package(?:_(.+))?\s*\(')

def get_split_packages(pkg: Path) -> Set[Tuple[str, str]]:
  packages: Set[Tuple[str, str]] = set()

  pkgbase = pkg.name

  pkgfile = pkg / 'package.list'
  if pkgfile.exists():
    with open(pkgfile) as f:
      packages.update((pkgbase, x) for x in f.read().split())
      return packages

  found = False
  try:
    with open(pkg / 'PKGBUILD') as f:
      for l in f:
        l = l.strip()
        m = _re_package.match(l)
        if m:
          found = True
          if m.group(1):
            packages.add((pkgbase, m.group(1)))
          else:
            packages.add((pkgbase, pkgbase))
  except FileNotFoundError:
    pass
  if not found:
    packages.add((pkgbase, pkgbase))
  return packages

def get_all_pkgnames(repodir: Path) -> Set[Tuple[str, str]]:
  packages: Set[Tuple[str, str]] = set()
  for pkg in lilacyaml.iter_pkgdir(repodir):
    packages.update(get_split_packages(pkg))
  return packages

