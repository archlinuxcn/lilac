import pathlib
from typing import Dict, Any

import yamlutils

# TODO: migrate to lilac2.api
import lilaclib

def load_lilac_yaml(dir: pathlib.Path) -> Dict[str, Any]:
  try:
    with open(dir / 'lilac.yaml') as f:
      conf = yamlutils.load(f)
  except FileNotFoundError:
    return {}

  update_on = conf.get('update_on')
  if update_on:
    for i, entry in enumerate(update_on):
      if isinstance(entry, str):
        update_on[i] = {entry: None}

  depends = conf.get('depends')
  if depends:
    for i, entry in enumerate(depends):
      if isinstance(entry, dict):
        depends[i] = next(iter(entry.items()))

  for func in ['pre_build', 'post_build', 'post_build_always']:
    name = conf.get(func)
    if name:
      funcvalue = getattr(lilaclib, name)
      conf[func] = funcvalue

  return conf
