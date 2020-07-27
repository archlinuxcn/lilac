from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Iterator
import importlib.resources

import yaml

from . import api
from .cmd import run_cmd

ALIASES: Dict[str, Any]

def _load_aliases() -> None:
  global ALIASES
  data = importlib.resources.read_text('lilac2', 'aliases.yaml')
  ALIASES = yaml.safe_load(data)

_load_aliases()

def iter_pkgdir(
  repodir: Path,
) -> Iterator[Path]:

  for x in run_cmd(['git', 'ls-files'], cwd=repodir, silent=True).split('\n'):
    if not x.endswith('lilac.yaml'):
      continue
    x = Path(x).parent

    yield x

def load_lilac_yaml(dir: Path) -> Dict[str, Any]:
  with open(dir / 'lilac.yaml') as f:
    conf = yaml.safe_load(f)

  if conf is None:
    return {}

  update_on = conf.get('update_on')
  if update_on:
    for i, entry in enumerate(update_on):
      if isinstance(entry, str):
        update_on[i] = {entry: ''}

  depends = conf.get('repo_depends')
  if depends:
    for i, entry in enumerate(depends):
      if isinstance(entry, dict):
        depends[i] = next(iter(entry.items()))
      else:
        depends[i] = entry, entry

  for func in ['pre_build', 'post_build', 'post_build_always']:
    name = conf.get(func)
    if name:
      funcvalue = getattr(api, name)
      conf[func] = funcvalue

  return conf
