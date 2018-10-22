import sys
import contextlib
import importlib.util
from pathlib import Path
from typing import Generator, cast, Dict, Tuple

from myutils import at_dir

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

    with at_dir(x):
      try:
        with load_lilac() as mod:
          mods[x.name] = mod
        if hasattr(mod, 'time_limit_hours') and mod.time_limit_hours < 0:
          raise ValueError('time_limit_hours should be positive.')
      except FileNotFoundError:
        pass
      except Exception:
        errors[x.name] = cast(ExcInfo, sys.exc_info())

  return mods, errors

@contextlib.contextmanager
def load_lilac() -> Generator[LilacMod, None, None]:
  try:
    spec = importlib.util.spec_from_file_location(
      'lilac.py', 'lilac.py')
    mod = spec.loader.load_module() # type: ignore

    yamlconf = load_lilac_yaml()
    for k, v in yamlconf:
      setattr(mod, k, v)

    yield cast(LilacMod, mod)
  finally:
    try:
      del sys.modules['lilac.py']
    except KeyError:
      pass

