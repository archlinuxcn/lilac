from __future__ import annotations

import pathlib
from typing import Dict, Any, Iterator, List
import importlib.resources

import yaml

from . import api
from .cmd import run_cmd

ALIASES: Dict[str, Any]
FUNCTIONS: List[str] = [
  'pre_build', 'post_build', 'post_build_always',
]


class NotLilacDirectory(Exception):
    pass

class LilacDirectory(type(Path())):

    def __init__(self, path):
        super().__init__()

        if not self.__is_in_git_repository__():
            raise NotLilacDirectory(f'{self} is not in a git repository')
        if not self.__has_lilac_mod__():
            raise NotLilacDirectory(f'No lilac.yaml in {self}')
        self.__check_lilac_mod__():

    def __is_in_git_repository__(self):
        if not self.is_dir():
            return False
        try:
            output = run_cmd(['git', 'rev-parse', '--is-inside-work-tree'], cwd=self, silent=True)
            if output == 'true\n':
                return True
        except:
            return False

    def __has_lilac_mod__(self):
        if not (self / 'lilac.yaml').is_file():
            return False
        return True

    def __check_lilac_mod__(self):
        # eg. timit_limit_hours > 0
        pass

def _load_aliases() -> None:
  global ALIASES
  data = importlib.resources.read_text('lilac2', 'aliases.yaml')
  ALIASES = yaml.safe_load(data)

_load_aliases()

def iter_pkgdir(
  repodir: pathlib.Path,
) -> Iterator[pathlib.Path]:

  for x in repodir.iterdir():
    if x.name[0] == '.':
      continue

    try:
        yield LilacDirectory(x)
    except:
      continue

def load_lilac_yaml(dir: pathlib.Path) -> Dict[str, Any]:
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

  for func in FUNCTIONS:
    name = conf.get(func)
    if name:
      funcvalue = getattr(api, name)
      conf[func] = funcvalue

  return conf
