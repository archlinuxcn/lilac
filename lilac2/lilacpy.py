import sys
import contextlib
import importlib.util
from pathlib import Path
from typing import Generator, cast, Dict, Tuple

from .typing import LilacMod, LilacMods, ExcInfo
from .lilacyaml import load_lilac_yaml

def load_all(repodir: Path) -> Tuple[LilacMods, Dict[str, ExcInfo]]:
  mods = {}
  errors = {}

  for x in repodir.iterdir():
    if not x.is_dir():
      continue

    if x.name[0] == '.':
      continue

    try:
      with load_lilac(x) as mod:
        mods[x.name] = mod
      if hasattr(mod, 'time_limit_hours') and mod.time_limit_hours < 0:
        raise ValueError('time_limit_hours should be positive.')
    except FileNotFoundError:
      pass
    except Exception:
      errors[x.name] = cast(ExcInfo, sys.exc_info())

  return mods, errors

@contextlib.contextmanager
def load_lilac(dir: Path) -> Generator[LilacMod, None, None]:
  try:
    spec = importlib.util.spec_from_file_location( # type: ignore # Path is accepted too
      'lilac.py', dir / 'lilac.py')
    mod = spec.loader.load_module() # type: ignore

    yamlconf = load_lilac_yaml(dir)
    for k, v in yamlconf.items():
      setattr(mod, k, v)

    mod = cast(LilacMod, mod)
    mod.pkgbase = dir.name
    yield mod

  finally:
    try:
      del sys.modules['lilac.py']
    except KeyError:
      pass

