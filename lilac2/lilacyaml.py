from __future__ import annotations

import pathlib
from typing import Dict, Any
import importlib.resources

import yaml

from . import api

ALIASES: Dict[str, Any]

def _load_aliases() -> None:
  """
  leads aliases from lilac2 and aliases.yaml
  :return:
  """
  global ALIASES
  data = importlib.resources.read_text('lilac2', 'aliases.yaml')
  ALIASES = yaml.safe_load(data)

_load_aliases()

def load_lilac_yaml(dir: pathlib.Path) -> Dict[str, Any]:
  """
  read yaml config (lilac.yaml) from path
  :param dir: the dir of lilac.yaml
  :return: configuration object, as specified in lilac-yaml-schema.py
  """
  with open(dir / 'lilac.yaml') as f:
    conf = yaml.safe_load(f)

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

  for func in ['pre_build', 'post_build', 'post_build_always']:
    name = conf.get(func)
    if name:
      funcvalue = getattr(api, name)
      conf[func] = funcvalue

  return conf
