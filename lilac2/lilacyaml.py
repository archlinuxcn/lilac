from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, cast
import importlib.resources
import sys
import datetime

import yaml

from .vendor.myutils import dehumantime

from . import api
from .const import _G, PACMAN_DB_DIR
from .typing import LilacInfo, LilacInfos, ExcInfo, NvEntries, OnBuildEntry

ALIASES: dict[str, Any] = {}
FUNCTIONS: list[str] = [
  'pre_build', 'post_build', 'post_build_always',
]

def _load_aliases() -> None:
  global ALIASES
  data = importlib.resources.files('lilac2').joinpath('aliases.yaml').read_text()
  ALIASES = yaml.safe_load(data)

_load_aliases()

def iter_pkgdir(repodir: Path) -> Iterator[Path]:
  for x in repodir.iterdir():
    if x.name[0] == '.':
      continue

    # leftover files, e.g. __pycache__ stuff
    if not (x / 'lilac.yaml').is_file():
      continue

    yield x

def load_lilac_yaml(dir: Path) -> dict[str, Any]:
  with open(dir / 'lilac.yaml') as f:
    conf = yaml.safe_load(f)

  if conf is None:
    return {}

  depends = conf.get('repo_depends')
  if depends:
    for i, entry in enumerate(depends):
      if isinstance(entry, dict):
        depends[i] = next(iter(entry.items()))
      else:
        depends[i] = entry, entry
  makedepends = conf.get('repo_makedepends')
  if makedepends:
    for i, entry in enumerate(makedepends):
      if isinstance(entry, dict):
        makedepends[i] = next(iter(entry.items()))
      else:
        makedepends[i] = entry, entry

  for func in FUNCTIONS:
    name = conf.get(func)
    if name:
      funcvalue = getattr(api, name)
      conf[func] = funcvalue

  return conf

def load_managed_lilacinfos(repodir: Path) -> tuple[LilacInfos, dict[str, ExcInfo]]:
  infos: LilacInfos = {}
  errors = {}

  for x in iter_pkgdir(repodir):
    try:
      info = load_lilacinfo(x)
      if not info.managed:
        continue
      if info.time_limit_hours < 0:
        raise ValueError('time_limit_hours should be positive.')
      infos[x.name] = info
    except Exception:
      errors[x.name] = cast(ExcInfo, sys.exc_info())

  return infos, errors

def load_lilacinfo(dir: Path) -> LilacInfo:
  yamlconf = load_lilac_yaml(dir)
  if update_on := yamlconf.get('update_on'):
    update_ons, throttle_info = parse_update_on(update_on)
  else:
    update_ons = []
    throttle_info = {}

  return LilacInfo(
    pkgbase = dir.absolute().name,
    maintainers = yamlconf.get('maintainers', []),
    update_on = update_ons,
    update_on_build = [OnBuildEntry(**x) for x in yamlconf.get('update_on_build', [])],
    throttle_info = throttle_info,
    repo_depends = yamlconf.get('repo_depends', []),
    repo_makedepends = yamlconf.get('repo_makedepends', []),
    time_limit_hours = yamlconf.get('time_limit_hours', 1),
    staging = yamlconf.get('staging', False),
    managed = yamlconf.get('managed', True),
    allowed_workers = yamlconf.get('allowed_workers', []),
  )

def expand_alias_arg(value: str) -> str:
  return value.format(
    pacman_db_dir = PACMAN_DB_DIR,
    repo_name = _G.reponame,
  )

def parse_update_on(
  update_on: list[dict[str, Any]],
) -> tuple[NvEntries, dict[int, datetime.timedelta]]:
  ret_update: NvEntries = []
  ret_throttle = {}

  for idx, entry in enumerate(update_on):
    t = entry.get('lilac_throttle')
    if t is not None:
      t_secs = dehumantime(t)
      ret_throttle[idx] = datetime.timedelta(seconds=t_secs)

    # fix wrong key for 'alpm-lilac'
    if entry.get('source') == 'alpm-lilac':
      del entry['source']
      entry['alias'] = 'alpm-lilac'

    alias = entry.pop('alias', None)

    # fill alpm-lilac parameters
    if alias == 'alpm-lilac':
      entry['source'] = 'alpm'
      entry.setdefault('dbpath', str(PACMAN_DB_DIR))
      entry.setdefault('repo', _G.reponame)

    elif alias is not None:
      for k, v in ALIASES[alias].items():
        if isinstance(v, str):
          entry.setdefault(k, expand_alias_arg(v))
        else:
          entry.setdefault(k, v)

    # fill our dbpath if not provided
    source = entry.get('source')
    if source == 'alpm' or source == 'alpmfiles':
      entry.setdefault('dbpath', str(PACMAN_DB_DIR))

    ret_update.append(entry)

  return ret_update, ret_throttle

