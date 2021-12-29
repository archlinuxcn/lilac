from __future__ import annotations

import sys
import contextlib
import importlib.util
from pathlib import Path
from typing import Generator, cast, Dict, Tuple

from .const import _G, PACMAN_DB_DIR
from .typing import LilacMod, LilacMods, ExcInfo
from .lilacyaml import (
  load_lilac_yaml, ALIASES, iter_pkgdir,
)
from . import api

def load_managed(repodir: Path) -> Tuple[LilacMods, Dict[str, ExcInfo]]:
  mods, errors = load_all(repodir)
  mods = {k: v for k, v in mods.items() if getattr(v, 'managed', True)}
  return mods, errors

def load_all(repodir: Path) -> Tuple[LilacMods, Dict[str, ExcInfo]]:
  mods: LilacMods = {}
  errors = {}

  for x in iter_pkgdir(repodir):
    try:
      with load_lilac(x) as mod:
        mods[x.name] = mod
      if hasattr(mod, 'time_limit_hours') and mod.time_limit_hours < 0:
        raise ValueError('time_limit_hours should be positive.')
    except FileNotFoundError:
      pass # ignore for now
    except Exception:
      errors[x.name] = cast(ExcInfo, sys.exc_info())

  return mods, errors

def expand_alias_arg(value: str) -> str:
  return value.format(
    pacman_db_dir=PACMAN_DB_DIR,
    repo_name=_G.repo.name,
  )

@contextlib.contextmanager
def load_lilac(dir: Path) -> Generator[LilacMod, None, None]:
  try:
    spec = importlib.util.spec_from_file_location(
      'lilac.py', dir / 'lilac.py')
    if spec is None:
      raise RuntimeError('lilac.py spec is None')
    mod = importlib.util.module_from_spec(spec)

    try:
      yamlconf = load_lilac_yaml(dir)
      g = None
      for k, v in yamlconf.items():
        if k.endswith('_script'):
          name = k[:-len('_script')]
          if name == 'post_build_always':
            code = [f'def {name}(success):']
          else:
            code = [f'def {name}():']
          for line in v.splitlines():
            code.append(f'  {line}')
          if g is None:
            g = vars(mod)
            # "import" lilac2.api
            g.update({a: b for a, b in api.__dict__.items()
                      if not a.startswith('_')})
          code_str = '\n'.join(code)
          # run code in `mod` namespace
          exec(code_str, g)
        else:
          setattr(mod, k, v)
    except FileNotFoundError:
      yamlconf = {}

    assert spec.loader
    try:
      spec.loader.exec_module(mod)
    except FileNotFoundError:
      if not yamlconf:
        raise FileNotFoundError('lilac.{yaml,py}')

    mod = cast(LilacMod, mod)
    mod.pkgbase = dir.name

    if hasattr(mod, 'update_on'):
      for entry in mod.update_on:

        # fix wrong key for 'alpm-lilac'
        if entry.get('source') == 'alpm-lilac':
          del entry['source']
          entry['alias'] = 'alpm-lilac'

        alias = entry.pop('alias', None)

        # fill alpm-lilac parameters
        if alias == 'alpm-lilac':
          entry['source'] = 'alpm'
          entry.setdefault('dbpath', str(PACMAN_DB_DIR))
          entry.setdefault('repo', _G.repo.name)

        elif alias is not None:
          for k, v in ALIASES[alias].items():
            if isinstance(v, str):
              entry.setdefault(k, expand_alias_arg(v))
            else:
              entry.setdefault(k, v)

        # fill our dbpath if not provided
        if entry.get('source') == 'alpm':
          entry.setdefault('dbpath', str(PACMAN_DB_DIR))

    yield mod

  finally:
    try:
      del sys.modules['lilac.py']
    except KeyError:
      pass
