from __future__ import annotations

from collections import defaultdict, namedtuple
from pathlib import Path
from typing import Dict, Union, Tuple, Set, Optional, DefaultDict
import re
import graphlib
from contextlib import suppress

from .vendor import archpkg

from .api import run_cmd
from .typing import LilacInfos
from . import lilacyaml

def get_dependency_map(
  depman: DependencyManager, lilacinfos: LilacInfos,
) -> Tuple[Dict[str, Set[Dependency]], Dict[str, Set[Dependency]]]:
  '''compute ordered, complete dependency relations between pkgbases (the directory names)

  This function does not make use of pkgname because they maybe the same for
  different pkgdir. Those are carried by Dependency and used elsewhere.

  The first returned dict has the complete set of dependencies of the given pkgbase, including
  build-time dependencies of other dependencies. The second dict has only the dependnecies
  required to be installed in the build chroot. For example, if A depends on B, and B makedepends
  on C, then the first dict has "A: {B, C}" while the second dict has only "A: {B}".
  '''
  map: DefaultDict[str, Set[Dependency]] = defaultdict(set)
  pkgdir_map: DefaultDict[str, Set[str]] = defaultdict(set)
  rmap: DefaultDict[str, Set[str]] = defaultdict(set)

  # same as above maps, but contain only normal dependencies, not makedepends or checkdepends
  norm_map: DefaultDict[str, Set[Dependency]] = defaultdict(set)
  norm_pkgdir_map: DefaultDict[str, Set[str]] = defaultdict(set)
  norm_rmap: DefaultDict[str, Set[str]] = defaultdict(set)

  for pkgbase, info in lilacinfos.items():
    for d in info.repo_depends:
      d = depman.get(d)

      pkgdir_map[pkgbase].add(d.pkgdir.name)
      rmap[d.pkgdir.name].add(pkgbase)
      map[pkgbase].add(d)

      norm_pkgdir_map[pkgbase].add(d.pkgdir.name)
      norm_rmap[d.pkgdir.name].add(pkgbase)
      norm_map[pkgbase].add(d)

    for d in info.repo_makedepends:
      d = depman.get(d)

      pkgdir_map[pkgbase].add(d.pkgdir.name)
      rmap[d.pkgdir.name].add(pkgbase)
      map[pkgbase].add(d)

  dep_order = graphlib.TopologicalSorter(pkgdir_map).static_order()
  for pkgbase in dep_order:
    if pkgbase in rmap:
      deps = map[pkgbase]
      dependers = rmap[pkgbase]
      for dd in dependers:
        map[dd].update(deps)
    if pkgbase in norm_rmap:
      deps = norm_map[pkgbase]
      dependers = norm_rmap[pkgbase]
      for dd in dependers:
        norm_map[dd].update(deps)

  build_dep_map: DefaultDict[str, Set[Dependency]] = defaultdict(set)
  for pkgbase, info in lilacinfos.items():
    build_deps = build_dep_map[pkgbase]
    build_deps.update(norm_map[pkgbase])
    for d in info.repo_makedepends:
      d = depman.get(d)
      build_deps.add(d)
      build_deps.update(norm_map[d.pkgdir.name])

  return map, build_dep_map

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
      ret = max(pkgs, key=lambda x: x.stat().st_mtime)
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

_re_package = re.compile(r'package(?:_(.+))?\(')

def get_split_packages(pkg: Path) -> Set[Tuple[str, str]]:
  packages: Set[Tuple[str, str]] = set()

  pkgbase = pkg.name

  pkgfile = pkg / 'package.list'
  if pkgfile.exists():
    with open(pkgfile) as f:
      packages.update((pkgbase, l.rstrip()) for l in f if not l.startswith('#'))
      return packages

  found = False
  with suppress(FileNotFoundError), open(pkg / 'PKGBUILD') as f:
    for l in f:
      if m := _re_package.match(l):
        found = True
        if m.group(1):
          packages.add((pkgbase, m.group(1).strip()))
        else:
          packages.add((pkgbase, pkgbase))
  if not found:
    packages.add((pkgbase, pkgbase))
  return packages

def get_all_pkgnames(repodir: Path) -> Set[Tuple[str, str]]:
  packages: Set[Tuple[str, str]] = set()
  for pkg in lilacyaml.iter_pkgdir(repodir):
    packages.update(get_split_packages(pkg))
  return packages

