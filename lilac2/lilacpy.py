import sys
import contextlib
import importlib.util
from pathlib import Path
from typing import Generator, cast, Dict, Tuple

from .typing import LilacMod, LilacMods, ExcInfo
from .lilacyaml import load_lilac_yaml, ALIASES

def load_all(repodir: Path) -> Tuple[LilacMods, Dict[str, ExcInfo]]:
  mods: LilacMods = {}
  errors = {}

  for x in repodir.iterdir():
    if not x.is_dir():
      continue

    if x.name[0] == '.':
      continue

    try:
      with load_lilac(x) as mod:
        if getattr(mod, 'managed', True):
          mods[x.name] = mod
      if hasattr(mod, 'time_limit_hours') and mod.time_limit_hours < 0:
        raise ValueError('time_limit_hours should be positive.')
    except FileNotFoundError:
      pass # ignore for now
    except Exception:
      errors[x.name] = cast(ExcInfo, sys.exc_info())

  return mods, errors

@contextlib.contextmanager
def load_lilac(dir: Path) -> Generator[LilacMod, None, None]:
  try:
    spec = importlib.util.spec_from_file_location( # type: ignore # Path is accepted too
      'lilac.py', dir / 'lilac.py')
    mod = importlib.util.module_from_spec(spec)

    try:
      yamlconf = load_lilac_yaml(dir)
      for k, v in yamlconf.items():
        setattr(mod, k, v)
    except FileNotFoundError:
      yamlconf = {}

    assert spec.loader
    try:
      spec.loader.exec_module(mod) # type: ignore
    except FileNotFoundError:
      if not yamlconf:
        raise FileNotFoundError('lilac.{yaml,py}')

    mod = cast(LilacMod, mod)
    mod.pkgbase = dir.name

    if hasattr(mod, 'update_on'):
      for i, entry in enumerate(mod.update_on):
        if 'alias' in entry:
          mod.update_on[i] = ALIASES[entry['alias']]

    yield mod

  finally:
    try:
      del sys.modules['lilac.py']
    except KeyError:
      pass

