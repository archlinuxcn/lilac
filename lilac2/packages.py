from collections import defaultdict
import os

import archpkg
from myutils import at_dir

def get_dependency_map(mods):
  ret = defaultdict(set)

  for name, mod in mods.items():
    depends = getattr(mod, 'depends', ())

class Dependency:
  _CACHE = {}

  @classmethod
  def get(cls, topdir, what):
    if isinstance(what, tuple):
      pkgbase, pkgname = what
    else:
      pkgbase = pkgname = what

    key = pkgbase, pkgname
    if key not in cls._CACHE:
      cls._CACHE[key] = cls(topdir, pkgbase, pkgname)
    return cls._CACHE[key]

  def __init__(self, topdir, pkgbase, pkgname):
    self.pkgbase = pkgbase
    self.pkgname = pkgname
    self.directory = os.path.join(topdir, pkgbase)

  def resolve(self):
    try:
      return self._find_local_package()
    except FileNotFoundError:
      return None

  def _find_local_package(self):
    with at_dir(self.directory):
      fnames = [x for x in os.listdir() if x.endswith('.pkg.tar.xz')]
      pkgs = []
      for x in fnames:
        info = archpkg.PkgNameInfo.parseFilename(x)
        if info.name == self.pkgname:
          pkgs.append(x)

      if len(pkgs) == 1:
        return os.path.abspath(pkgs[0])
      elif not pkgs:
        raise FileNotFoundError
      else:
        ret = sorted(
          pkgs, reverse=True, key=lambda n: os.stat(n).st_mtime)[0]
        return os.path.abspath(ret)

